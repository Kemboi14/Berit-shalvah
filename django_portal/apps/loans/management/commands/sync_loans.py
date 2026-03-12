# -*- coding: utf-8 -*-
"""
Management commands for Django-Odoo synchronization
"""
from django.core.management.base import BaseCommand
from apps.loans.odoo_sync import EnhancedOdooIntegration
from apps.loans.models import LoanApplication
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize all loans between Django and Odoo'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--test-connection',
            action='store_true',
            help='Test connection to Odoo',
        )
        parser.add_argument(
            '--sync-all',
            action='store_true',
            help='Sync all loans between Django and Odoo',
        )
        parser.add_argument(
            '--sync-django-to-odoo',
            action='store_true',
            help='Sync Django loans to Odoo only',
        )
        parser.add_argument(
            '--sync-odoo-to-django',
            action='store_true',
            help='Sync Odoo loans to Django only',
        )
    
    def handle(self, *args, **options):
        try:
            integration = EnhancedOdooIntegration()
            
            if options['test_connection']:
                self.test_connection(integration)
            elif options['sync_all']:
                self.sync_all_loans(integration)
            elif options['sync_django_to_odoo']:
                self.sync_django_to_odoo(integration)
            elif options['sync_odoo_to_django']:
                self.sync_odoo_to_django(integration)
            else:
                self.print_help('manage.py', 'sync_loans')
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            )
    
    def test_connection(self, integration):
        """Test connection to Odoo"""
        self.stdout.write('Testing Odoo connection...')
        
        result = integration.test_connection()
        
        if result['status'] == 'connected':
            self.stdout.write(
                self.style.SUCCESS('✓ Connected to Odoo successfully')
            )
            self.stdout.write(f"Odoo Version: {result['odoo_version']}")
            self.stdout.write(f"Databases: {result['databases']}")
            self.stdout.write(f"Loan Model Found: {result['loan_model_found']}")
        else:
            self.stdout.write(
                self.style.ERROR(f'✗ Connection failed: {result["error"]}')
            )
    
    def sync_all_loans(self, integration):
        """Sync all loans between Django and Odoo"""
        self.stdout.write('Starting complete synchronization...')
        
        result = integration.sync_all_loans()
        
        if 'error' in result:
            self.stdout.write(
                self.style.ERROR(f'Sync failed: {result["error"]}')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Sync completed:')
        )
        self.stdout.write(f"  Django → Odoo: {result['django_to_odoo']} loans")
        self.stdout.write(f"  Odoo → Django: {result['odoo_to_django']} loans")
        
        if result['errors']:
            self.stdout.write(
                self.style.WARNING('Errors encountered:')
            )
            for error in result['errors']:
                self.stdout.write(f"  - {error}")
    
    def sync_django_to_odoo(self, integration):
        """Sync Django loans to Odoo only"""
        self.stdout.write('Syncing Django loans to Odoo...')
        
        applications = LoanApplication.objects.filter(
            odoo_application_id__isnull=True
        ).exclude(status__in=['draft'])
        
        count = 0
        for application in applications:
            try:
                odoo_id = integration.create_loan_application(application)
                application.odoo_application_id = odoo_id
                application.save()
                count += 1
                self.stdout.write(f"✓ Synced {application.reference_number}")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Error syncing {application.reference_number}: {str(e)}")
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Synced {count} loans to Odoo')
        )
    
    def sync_odoo_to_django(self, integration):
        """Sync Odoo loans to Django only"""
        self.stdout.write('Syncing Odoo loans to Django...')
        
        # Get all Odoo applications with portal references
        odoo_applications = integration.models.execute_kw(
            integration.odoo_db, integration.uid, integration.odoo_password,
            'berit.loan.application', 'search',
            [[['portal_application_ref', '!=', '']]]
        )
        
        count = 0
        for odoo_id in odoo_applications:
            try:
                odoo_data = integration.models.execute_kw(
                    integration.odoo_db, integration.uid, integration.odoo_password,
                    'berit.loan.application', 'read',
                    [odoo_id],
                    {'fields': ['name', 'state', 'portal_application_ref', 'approval_date', 'disbursement_date']}
                )
                
                if odoo_data:
                    odoo_app = odoo_data[0]
                    portal_ref = odoo_app.get('portal_application_ref')
                    
                    if portal_ref:
                        django_app = LoanApplication.objects.filter(
                            reference_number=portal_ref
                        ).first()
                        
                        if django_app:
                            old_status = django_app.status
                            new_status = integration._map_odoo_status(odoo_app.get('state'))
                            
                            if new_status and old_status != new_status:
                                django_app.status = new_status
                                if odoo_app.get('approval_date'):
                                    django_app.approved_at = timezone.now()
                                if odoo_app.get('disbursement_date'):
                                    django_app.disbursed_at = timezone.now()
                                django_app.save()
                                count += 1
                                self.stdout.write(f"✓ Updated {django_app.reference_number}")
            
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Error syncing Odoo loan {odoo_id}: {str(e)}")
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Updated {count} loans from Odoo')
        )
