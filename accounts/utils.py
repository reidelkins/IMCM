import traceback
from typing import Dict, Any
from datetime import datetime, timedelta
from .models import Company, Franchise, CustomUser
from .serializers import CompanySerializer, UserSerializerWithToken

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template


def makeCompany(companyName, email, phone, stripeId):
    try:
        comp = {'name': companyName, 'phone': phone, 'email': email, 'stripeID': stripeId}
        serializer = CompanySerializer(data=comp)
        if serializer.is_valid():
            company = serializer.save()
            if company:
                mail_subject = "Access Token for Is My Customer Moving"
                messagePlain = "Your access token is: " + company.accessToken
                messagePlain = "Thank you for signing up for Is My Customer Moving. Your company name is: " + company.name +  "and your access token is: " + company.accessToken + ". Please use this info at https://app.ismycustomermoving.com/register to create your account."
                message = get_template("registration.html").render({
                    'company': company.name, 'accessToken': company.accessToken
                })
                send_mail(subject=mail_subject, message=messagePlain, from_email=settings.EMAIL_HOST_USER, recipient_list=[email], html_message=message, fail_silently=False)
                return company
            else:
                return {'Error': "Company with that name already exists"}
        else:
            print(serializer.errors)
            return {'Error': 'Serializer not valid'}
    except Exception as e:
        print(e)
        return {'Error': f'{e}'}
            
# find franchise that is the closest to the area provided for the referral
def find_franchise(area, franchise, referredFrom):
    try:
        franchise = Franchise.objects.get(id=franchise)
        
        if area:
            companies = list(Company.objects.filter(franchise=franchise).exclude(id=referredFrom).values_list('id', flat=True))
            return companies[0]
        else:
            return None
    except Exception as e:
        print("finding franchise failed")
        print(f"ERROR: {e}")
        print(traceback.format_exc())


