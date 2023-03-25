from django.core.management.base import BaseCommand


from data.utils import send_update_email


class Command(BaseCommand):
    help = 'Send an email to all users with the template name provided'

    def add_arguments(self , parser):
        parser.add_argument('-t', '--template')
    
    def handle(self, *args, **options):        
        template = options['template']
        send_update_email(template)        