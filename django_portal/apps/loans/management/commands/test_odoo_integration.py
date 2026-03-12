"""
Management command to test and initialize Odoo integration
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.loans.enhanced_tasks import test_odoo_connection, complete_sync_all_loans
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test Odoo connection and perform initial synchronization'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Perform complete synchronization after testing connection',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force synchronization even if applications are already synced',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔗 Testing Odoo Integration...\n')
        )

        # Test Odoo connection
        try:
            result = test_odoo_connection()
            if 'successful' in result.lower():
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Odoo Connection: {result}')
                )
            else:
                raise CommandError(f'❌ Odoo Connection Failed: {result}')
        except Exception as e:
            raise CommandError(f'❌ Odoo Connection Error: {str(e)}')

        # Test synchronization if requested
        if options['sync']:
            self.stdout.write(
                self.style.WARNING('\n🔄 Performing Complete Synchronization...\n')
            )

            try:
                sync_result = complete_sync_all_loans()

                if isinstance(sync_result, dict) and 'error' not in sync_result:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Synchronization Completed Successfully!')
                    )
                    self.stdout.write(f'   📤 Django → Odoo: {sync_result.get("django_to_odoo", 0)} applications')
                    self.stdout.write(f'   📥 Odoo → Django: {sync_result.get("odoo_to_django", 0)} updates')

                    if sync_result.get('errors'):
                        self.stdout.write(
                            self.style.WARNING(f'   ⚠️  {len(sync_result["errors"])} errors occurred:')
                        )
                        for error in sync_result['errors'][:5]:  # Show first 5 errors
                            self.stdout.write(f'      • {error}')
                else:
                    raise CommandError(f'❌ Synchronization Failed: {sync_result}')

            except Exception as e:
                raise CommandError(f'❌ Synchronization Error: {str(e)}')

        # Display configuration info
        self.stdout.write(
            self.style.INFO('\n📋 Configuration Summary:')
        )
        self.stdout.write(f'   🌐 Odoo URL: {getattr(settings, "ODOO_URL", "Not configured")}')
        self.stdout.write(f'   🗄️  Database: {getattr(settings, "ODOO_DB", "Not configured")}')
        self.stdout.write(f'   👤 Username: {getattr(settings, "ODOO_USERNAME", "Not configured")}')

        # Display Celery beat schedule
        if hasattr(settings, 'CELERY_BEAT_SCHEDULE'):
            self.stdout.write(
                self.style.INFO('\n⏰ Automatic Sync Schedule:')
            )
            for task_name, task_config in settings.CELERY_BEAT_SCHEDULE.items():
                schedule = task_config.get('schedule', 'Unknown')
                if hasattr(schedule, 'schedule'):
                    # Handle crontab schedules
                    schedule_info = f"crontab({schedule._orig_minute}, {schedule._orig_hour})"
                else:
                    schedule_info = str(schedule)
                self.stdout.write(f'   🔄 {task_name}: {schedule_info}')

        self.stdout.write(
            self.style.SUCCESS('\n🎉 Odoo Integration Setup Complete!')
        )
        self.stdout.write(
            self.style.INFO('💡 Use --sync flag to perform full synchronization')
        )
