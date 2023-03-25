import pytest
import pyotp
import re
from unittest.mock import patch
from django.core.mail import send_mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Company, CustomUser, InviteToken
from .utils import makeCompany

@pytest.fixture
def company():
    return makeCompany("Test Company", "testcompany@gmail.com", "8881234567", "testStripeId1234")

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def authenticated_user(api_client, company):
    url = reverse('register')
    data = {
        'firstName': 'John',
        'lastName': 'Doe',
        'email': 'test@gmail.com',
        'password': 'password',
        'company': company.name,
        'accessToken': company.accessToken,
        'phone': '8881234567'
    }
    api_client.post(url, data, format='json')
    return CustomUser.objects.get(email="test@gmail.com")

@pytest.fixture
def invited_info(company):
    email = "anothertest@gmail.com"
    user = CustomUser.objects.create(
        email=email,
        company=company,
        status='pending'
    )
    inviteToken = InviteToken.objects.create(company=company, email=email)
    return (inviteToken, user)

@pytest.mark.django_db
def test_company_crud():
    company = Company.objects.create(
        name='Some Company', email="somecompany@gmail.com", phone="8881234567"
    )
    assert company.name == 'Some Company'
    assert company.email == 'somecompany@gmail.com'
    assert company.phone == '8881234567'
    assert str(company) == 'Some Company'

    company.name = 'Some Other Company'
    company.save()
    assert company.name == 'Some Other Company'
    assert str(company) == 'Some Other Company'

    company.delete()
    assert Company.objects.filter(name="Some Other Company").count() == 0

@pytest.mark.django_db
def test_customuser_crud():
    company = Company.objects.create(
        name='Some Company'
    )
    user = CustomUser.objects.create(
        first_name='john', last_name='doe', company=company, email="johndoe@gmail.com", password="testpass123"
    )
    assert user.first_name == 'john'
    assert user.last_name == 'doe'
    assert user.company == company
    assert str(user) == 'johndoe@gmail.com'

    user.first_name = 'jane'
    user.save()
    assert user.first_name == 'jane'

    # Test Default Variables
    assert user.is_active == True
    assert user.isVerified == False
    assert user.is_staff == False
    assert user.is_superuser == False

    user.delete()
    assert CustomUser.objects.filter(first_name="jane").count() == 0
    
@pytest.mark.django_db
def test_makeCompany(company):
    
    assert company.name == "Test Company"
    assert company.email == "testcompany@gmail.com"
    assert company.phone == "8881234567"
    assert company.stripeID == "testStripeId1234"
    assert company.accessToken != None


@pytest.mark.django_db
def test_register(api_client, company):
    url = reverse('register')
    # Test Faulty Company Name
    data = {
        'firstName': 'John',
        'lastName': 'Doe',
        'email': 'test@gmail.com',
        'password': 'password',
        'company': "Not a Company",
        'accessToken': company.accessToken,
        'phone': '8881234567'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 400

    # Test Faulty Access Token
    data = {
        'firstName': 'John',
        'lastName': 'Doe',
        'email': 'test@gmail.com',
        'password': 'password',
        'company': company.name,
        'accessToken': "wrongAccessToken",
        'phone': '8881234567'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 400

    # Test Proper Registration
    data = {
        'firstName': 'John',
        'lastName': 'Doe',
        'email': 'test@gmail.com',
        'password': 'password',
        'company': company.name,
        'accessToken': company.accessToken,
        'phone': '8881234567'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 200
    assert CustomUser.objects.filter(email="test@gmail.com").count() == 1
    
    user = CustomUser.objects.get(email="test@gmail.com")
    assert user.isVerified == True

    # Test Duplicate Email
    response = api_client.post(url, data, format='json')
    assert response.status_code == 400

    # Test Duplicate Registration
    data = {
        'firstName': 'John',
        'lastName': 'Doe',
        # email has changed
        'email': 'test2@gmail.com',
        'password': 'password',
        'company': company.name,
        'accessToken': company.accessToken,
        'phone': '8881234567'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 400

    
@pytest.mark.django_db
def test_login(api_client, authenticated_user):
    
    response = api_client.get(reverse('login'))
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    url = reverse('login')
    data = {'email': authenticated_user.email, 'password': 'wrongpassword'}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    url = reverse('login')
    data = {'email': 'wrongemail', 'password': 'password'}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    data = {'email': authenticated_user.email, 'password': 'password'}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert 'access' in response.json()
    assert 'refresh' in response.json()

@pytest.mark.django_db
def test_otp(api_client, authenticated_user):
    assert authenticated_user.otp_enabled == False
    assert authenticated_user.otp_verified == False
    assert authenticated_user.otp_base32 == None
    assert authenticated_user.otp_auth_url == None

    url = reverse('otp-generate')
    data = {'id': authenticated_user.id}
    response = api_client.post(url, data, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['otp_base32'] != None
    assert response.json()['otp_auth_url'] != None

    url = reverse('otp-verify')
    otp = pyotp.TOTP(response.json()['otp_base32']).now()
    data = {'id': authenticated_user.id, 'otp': otp}
    response = api_client.post(url, data, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['otp_enabled'] == True

    url = reverse('otp-validate')
    otp = pyotp.TOTP(response.json()['otp_base32']).now()
    data = {'id': authenticated_user.id, 'otp': otp}
    response = api_client.post(url, data, format='json')

    assert response.status_code == status.HTTP_200_OK

    url = reverse('otp-disable')
    data = {'id': authenticated_user.id}
    response = api_client.post(url, data, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['otp_enabled'] == False
    assert response.json()['otp_base32'] == None
    assert response.json()['otp_auth_url'] == None


@pytest.mark.django_db
def test_get_users(api_client, authenticated_user, invited_info):
    url = reverse('user-list', kwargs={'company':str(authenticated_user.company.id)})
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 2

@pytest.mark.django_db
def test_make_extra_user(api_client, authenticated_user, invited_info):
    EMAIL = "anothertest@gmail.com"
    # Test Invite User
    url = reverse('manageuser', kwargs={'id':str(authenticated_user.company.id)})
    data = {
        'email': EMAIL,
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    emails = [user['email'] for user in response.json()]
    assert EMAIL in emails
    assert response.json()[0]['status'] == "pending" or response.json()[1]['status'] == "pending"
    assert "test@gmail.com" in emails
    
    invite_token, invited_user = invited_info
    # Test Accept Invite With Wrong Email
    url = reverse('manageuser', kwargs={'id':str(invite_token.id)})
    data = {
        'email': "wrongemail@gmail.com"
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Test Accept Invite With Right Email
    data = {
        'email': EMAIL,
        'password': 'password',
        'firstName': 'Bob',
        'lastName': 'Smith',
        'phone': '7775643265'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['email'] == EMAIL
    assert response.json()['status'] == "active"
    assert response.json()['isVerified'] == True

    # Test Make User Admin
    url = reverse('manageuser', kwargs={'id':str(invited_user.id)})
    response = api_client.post(url)
    assert response.status_code == status.HTTP_200_OK
    for user in response.json():
        if user['email'] == EMAIL:
            assert user['status'] == 'admin'

    # Test Bad ID Provided
    url = reverse('manageuser', kwargs={'id': 'badid'})
    response = api_client.post(url)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_update_user(api_client, authenticated_user):
    # Test Update User
    url = reverse('manageuser', kwargs={'id':str(authenticated_user.id)})
    assert authenticated_user.first_name == "John"
    assert authenticated_user.last_name == "Doe"
    assert authenticated_user.email == "test@gmail.com"
    data = {
        'email': 'newtest@gmail.com',
        'firstName': 'Bob',
        'lastName': 'Smith',
    }
    response = api_client.put(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['email'] == 'newtest@gmail.com'
    assert response.json()['first_name'] == 'Bob'
    assert response.json()['last_name'] == 'Smith'

    # Test Bad ID Provided
    url = reverse('manageuser', kwargs={'id':'badid'})
    response = api_client.put(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # Test Bad Data Provided
    url = reverse('manageuser', kwargs={'id':str(authenticated_user.id)})
    data = {
        'email': 'newtest@gmail.com',
        'firstName': 'Bob',
    }
    response = api_client.put(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = {
        'lastName': 'newtest@gmail.com',
        'firstName': 'Bob',
    }
    response = api_client.put(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = {
        'email': 'newtest@gmail.com',
        'lastName': 'Bob',
    }
    response = api_client.put(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
def test_delete_user(api_client, authenticated_user, invited_info):
    assert CustomUser.objects.count() == 2
    secondUser = invited_info[1]
    # Test Delete Single User
    url = reverse('manageuser', kwargs={'id':str(authenticated_user.company.id)})
    data = [secondUser.id]
    response = api_client.delete(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1
    
    # Test Delete Multiple Users
    data = [authenticated_user.id, secondUser.id]
    response = api_client.delete(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 0

@pytest.mark.django_db
def test_reset_password(api_client, authenticated_user):
    url = reverse('password_reset:reset-password-request')
    data = {
        'email': authenticated_user.email
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK

    # Test Bad Email
    data = {
        'email': 'wrong@gmail.com'
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

# @pytest.mark.django_db
# @patch.object(send_mail, 'delay')  # mock send_mail function
# def test_reset_password(mock_send_mail, api_client, authenticated_user):
#     url = reverse('password_reset:reset-password-request')
#     # Extract the password reset token from the email body
#     assert mock_send_mail.called  # check that the send_mail function was called
#     email_args, email_kwargs = mock_send_mail.call_args
#     assert email_kwargs['subject'] == 'Password reset request'
#     assert email_kwargs['recipient_list'] == [authenticated_user.email]
#     match = re.search(r'http://.+/reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z_\-]+)/', email_kwargs['message'])
#     assert match is not None
#     uidb64 = match.group('uidb64')
#     token = match.group('token')

#     # Test password reset confirmation with the generated token
#     url = reverse('password_reset:reset-password-confirm', kwargs={'uidb64': uidb64, 'token': token})
#     data = {
#         'new_password1': 'newpassword',
#         'new_password2': 'newpassword'
#     }
#     response = api_client.post(url, data, format='json')
#     assert response.status_code == status.HTTP_200_OK
#     assert response.data['detail'] == 'Password has been reset with the new password.'








