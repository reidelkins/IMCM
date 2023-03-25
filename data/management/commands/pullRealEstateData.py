from django.core.management.base import BaseCommand
from datetime import datetime


from data.utils import auto_update


class Command(BaseCommand):
    help = 'Scrape data from realtor.com and update the database'

    def add_arguments(self , parser):
        parser.add_argument('-c', '--company')
    
    def handle(self, *args, **options):
        company = options['company']
        if company:
            auto_update.delay(company)
        else:
            daysToRun = [0, 1, 2, 3, 4]
            dt = datetime.now()
            weekday = dt.weekday()
            if weekday in daysToRun:
                auto_update.delay()