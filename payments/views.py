from django.conf import settings
from django.template.loader import get_template
from django.core.mail import send_mail
from accounts.models import Company, CustomUser
from accounts.utils import makeCompany
# from data.utils import deleteExtraClients
from datetime import datetime, timedelta

from djstripe import webhooks, models as djstripe_models

import stripe

stripe.api_key = settings.STRIPE_TEST_SECRET_KEY

# @api_view(['POST' ])
# def save_stripe_info(request):
#     if request.method == 'POST':
#         data = request.data
#         email = data['email']
#         company = data['company']
#         phone = data['phone']
#         payment_method_id = data['payment_method_id']
#         try:
#             product = Product.objects.get(tier=data['tier'], timeFrame=data['timeFrame'])
#         except Product.DoesNotExist:
#             print("Product does not exist")
#             return Response("Product does not exist", status=status.HTTP_400_BAD_REQUEST)
#         extra_msg = ''
#         customer_data = stripe.Customer.list(email=email).data
#         if len(customer_data) == 0:
#             customer = stripe.Customer.create(
#             email=email, payment_method=payment_method_id, name=company, invoice_settings={
#                 'default_payment_method': payment_method_id
#             })
#         else:
#             customer = customer_data[0]
#             extra_msg = 'Customer already exists.'
        
#         trialEnd = int((datetime.now()+ timedelta(days=7)).timestamp())
#         subscription = stripe.Subscription.create(
#             customer=customer,
#             items=[
#                 {
#                 'price': product.pid
#                 }
#             ],
#             trial_end=trialEnd
#         )
#         comp = makeCompany(company, email, phone, customer.id)
#         comp.product = product
#         comp.save()
#         if type(comp) == dict:
#             print("company equals dict")
#             return Response(comp, status=status.HTTP_400_BAD_REQUEST)
#         return Response(status=status.HTTP_200_OK, 
#             data={
#                 'message': 'Success', 
#                 'data': {'customer_id': customer.id,
#                 'extra_msg': extra_msg,
#                 'sub_id':  subscription,
#                 } }  
#         )

# @api_view(['POST'])
# def setup_intent(request):
#     if request.method == 'POST':
#         intent = stripe.SetupIntent.create(
#             payment_method_types=['card'],
#         )
#         return Response(status=status.HTTP_200_OK,
#             data={
#                 'message': 'Success',
#                 'data': {'client_secret': intent.client_secret } }
#         )
        
# @api_view(['GET'])
# def publishable_key(request):
#     if request.method == 'GET':
#         return Response(status=status.HTTP_200_OK,
#             data={
#                 'message': 'Success',
#                 'data': {'publishable_key': settings.STRIPE_PUBLISHABLE_KEY } }
#         )


# when customer/subscription created 
@webhooks.handler('customer.created')
def create_customer(event: djstripe_models.Event):
    print("customer created")
#     obj = event.data['object']
#     company = obj['name']
#     email = obj['email']
#     stripeID = obj['id']
#     phone = obj['phone']
#     try:
#         Company.objects.get(name=company, email=email, stripeID=stripeID)
#     except:
#         makeCompany(company, email, phone, stripeID)
#     print("done")


# # important in the case that company adds back a canceled subscription
@webhooks.handler('customer.subscription.created')
def create_subscription(event: djstripe_models.Event):
    print("subscription created")
#     try:
#         obj = event.data['object']
#         customer = djstripe_models.Customer.objects.get(id=obj['customer'])
#         company = Company.objects.get(email=customer.email)
#         product = Product.objects.get(pid=obj['items']['data'][0]['price']['id'])
#         company.product = product
#         company.save()
#         users = CustomUser.objects.filter(company=company)
#         for user in users:
#             user.isVerified = True
#             user.save()
#     except Exception as e:
#         print(e)
#         print("error")

@webhooks.handler('checkout.session.completed')
def completed_checkout(event: djstripe_models.Event):
    try:
        obj = event.data['object']
        phone = obj['customer_details']['phone']
        email = obj['customer_details']['email']
        companyName = obj['custom_fields'][0]['text']['value']
        stripeId = obj['customer']
        subscription = djstripe_models.Subscription.objects.get(id=obj['subscription'])
        plan = subscription.plan
        try:
            company = Company.objects.get(name=companyName, email=email, stripeID=stripeId)
        except:
            try:
                company = makeCompany(companyName, email, phone, stripeId)
                company.product = plan
                company.save()
            except Exception as e:
                print(f"error: {e}")
                
        users = CustomUser.objects.filter(company=company)
        for user in users:
            user.isVerified = True
            user.save()
        # deleteExtraClients(company.id)
    except Exception as e:
                print(f"error: {e}")
            


#canceled subscription
@webhooks.handler('customer.subscription.deleted')
def cancel_subscription(event: djstripe_models.Event):
    try:
        obj = event.data['object']
        customer = djstripe_models.Customer.objects.get(id=obj['customer'])
        company = Company.objects.get(email=customer.email)
        product = djstripe_models.Plan.objects.get(id="price_1MhxfPAkLES5P4qQbu8O45xy")
        company.product = product
        company.save()
        users = CustomUser.objects.filter(company=company)
        for user in users:
            user.isVerified = False
            user.save()
            mail_subject = "Subscription Ended: Is My Customer Moving"
            # send the endedSubscrition email to each user
            messagePlain = f"Your subscription to Is My Customer Moving has ended. Please contact us at reid@ismycustomermoving.com to reactivate your subscription."
            message = get_template("endedSubscription.html").render({'email': user.email})
            send_mail(subject=mail_subject, message=messagePlain, from_email=settings.EMAIL_HOST_USER, recipient_list=[user.email], html_message=message, fail_silently=False)    
    except Exception as e:
        print(e)
        print("error")

@webhooks.handler('customer.subscription.updated')
def update_subscription(event: djstripe_models.Event):
    try:
        obj = event.data['object']
        customer = djstripe_models.Customer.objects.get(id=obj['customer'])

        plan = djstripe_models.Subscription.objects.filter(customer=obj['customer']).values('plan')
        plan = plan[0]['plan']
        company = Company.objects.get(email=customer.email)
        plan = djstripe_models.Plan.objects.get(djstripe_id=plan)
        
        company.product = plan
        company.save()
        # if plan != "price_1MhxfPAkLES5P4qQbu8O45xy":
        #     deleteExtraClients(company.id)
    except Exception as e:
        print(e)
        print("error")
    

# @webhooks.handler('payment_method.detached')
# def remove_detached_payment_method(event: djstripe_models.Event):
#     obj = event.data['object']
#     djstripe_models.PaymentMethod.objects.filter(id=obj['id']).delete()


# @webhooks.handler('invoice.payment_failed', 'invoice.payment_action_required')
# def cancel_trial_subscription_on_payment_failure(event: djstripe_models.Event):
#     obj = event.data['object']
#     subscription_id = obj.get('subscription', None)

#     subscription: djstripe_models.Subscription = djstripe_models.Subscription.objects.get(id=subscription_id)

#     # Check if the previous subscription period was trialing
#     # Unfortunately status field is already updated to active at this point
#     if subscription.current_period_start == subscription.trial_end:
#         subscription.cancel(at_period_end=False)


# @webhooks.handler('invoice.payment_failed', 'invoice.payment_action_required')
# def send_email_on_subscription_payment_failure(event: djstripe_models.Event):
#     """
#     This is an example of a handler that sends an email to a customer after a recurring payment fails

#     :param event:
#     :return:
#     """
#     notifications.SubscriptionErrorEmail(customer=event.customer).send()


# @webhooks.handler('customer.subscription.trial_will_end')
# def send_email_trial_expires_soon(event: djstripe_models.Event):
#     obj = event.data['object']
#     expiry_date = timezone.datetime.fromtimestamp(obj['trial_end'], tz=timezone.timezone.utc)
#     notifications.TrialExpiresSoonEmail(customer=event.customer, data={'expiry_date': expiry_date}).send()
