from django.core.management.base import BaseCommand
from datetime import datetime

from data.utils import sendDailyEmail

class Command(BaseCommand):
    help = 'Sends the email to each user with their data'

    def add_arguments(self , parser):
        parser.add_argument('-c', '--company')
    
    def handle(self, *args, **options):
        company = options['company']
        if company:
            sendDailyEmail.delay(company)
        else:
            daysToRun = [0, 1, 2, 3, 4]
            dt = datetime.now()
            weekday = dt.weekday()
            if weekday in daysToRun:
                sendDailyEmail.delay()