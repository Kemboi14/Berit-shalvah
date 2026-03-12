from django.core.management.base import BaseCommand
from django.conf import settings
from apps.loans.enhanced_tasks import test_odoo_connection, complete_sync_all_loans


class Command(BaseCommand):
    help = 'Test Odoo connection and perform initial synchronization'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Perform complete synchronization after testing connection',
        )

    def handle(self, *args, **options):
        self.stdout.write('🔗 Testing Odoo Integration...\n')

        # Test connection
        result = test_odoo_connection()
        if 'successful' in result.lower():
            self.stdout.write(self.style.SUCCESS(f'✅ Connection: {result}'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ Connection Failed: {result}'))
            return

        if options['sync']:
            self.stdout.write('🔄 Performing Complete Synchronization...\n')
            sync_result = complete_sync_all_loans()

            if isinstance(sync_result, dict) and 'error' not in sync_result:
                self.stdout.write(self.style.SUCCESS('✅ Sync Completed!'))
                self.stdout.write(f'   Django→Odoo: {sync_result.get("django_to_odoo", 0)} apps')
                self.stdout.write(f'   Odoo→Django: {sync_result.get("odoo_to_django", 0)} updates')
            else:
                self.stdout.write(self.style.ERROR(f'❌ Sync Failed: {sync_result}'))

        self.stdout.write(self.style.SUCCESS('\n🎉 Odoo Integration Ready!'))
        self.stdout.write('⏰ Automatic sync scheduled every 5-30 minutes')
