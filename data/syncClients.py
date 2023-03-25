from celery import shared_task
import requests
import gc
from time import sleep

from datetime import datetime
from django.conf import settings
from django.db.models.functions import Coalesce

from accounts.models import Company
from .models import Client, Task
from .utils import saveClientList, updateClientList, doItAll, deleteExtraClients, delVariables
from simple_salesforce import Salesforce



@shared_task
def get_fieldEdge_clients(company_id, task_id):
    company = Company.objects.get(id=company_id)

@shared_task
def get_hubspot_clients(company_id, task_id):
    company = Company.objects.get(id=company_id)

@shared_task
def get_salesforce_clients(company_id, task_id=None):
    company = Company.objects.get(id=company_id)

    sf = Salesforce(
        instance_url="https://ismycustomermoving-dev-ed.develop.my.salesforce.com",
        session_id=company.sfAccessToken,
        consumer_key=settings.SALESFORCE_CONSUMER_KEY, 
        consumer_secret=settings.SALESFORCE_CONSUMER_SECRET)
    
    contacts = sf.query("SELECT FirstName, LastName, Phone, MailingStreet FROM Contact")
    clients=[]
    count = 0
    for contact in contacts['records']:
    
        x = contact['MailingStreet']
        count += 1
        if x != None:
            x = x.split('\n')
            if len(x) > 1:
                street = x[0]
                x = x[1].replace(',', '')
                x = x.split(' ')
                if len(x) == 3 and street != None:
                    client = {
                        "name": f"{contact['FirstName']} {contact['LastName']}",                
                        "phone number": contact['Phone'],
                        "address": street,
                        "city": x[0],
                        "state": x[1],
                        "zip code": x[2],
                    }
                    clients.append(client)
        

    saveClientList(clients, company_id)

    # bulk = SalesforceBulk(sessionId="https://login.salesforce.com/id/00DDn00000DsoYnMAJ/005Dn000007Eo6XIAS", host="https://ismycustomermoving-dev-ed.develop.my.salesforce.com")
    # job = bulk.create_query_job("Contact", contentType='JSON')
    # batch = bulk.query(job, "select Id,LastName from Contact")
    # bulk.close_job(job)
    # while not bulk.is_batch_done(batch):
    #     time.sleep(10)

    # for result in bulk.get_all_results_for_query_batch(batch):
    #     result = json.load(IteratorBytesIO(result))
    #     for row in result:
    #         print(row) # dictionary rows
    


@shared_task
def get_serviceTitan_clients(company_id, task_id):
    company = Company.objects.get(id=company_id)
    tenant = company.tenantID
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = f'grant_type=client_credentials&client_id={company.clientID}&client_secret={company.clientSecret}'
    response = requests.post('https://auth.servicetitan.io/connect/token', headers=headers, data=data)    

    headers = {'Authorization': response.json()['access_token'], 'Content-Type': 'application/json', 'ST-App-Key': settings.ST_APP_KEY}
    clients = []
    moreClients = True
    #get client data
    page = 1
    while(moreClients):
        response = requests.get(f'https://api.servicetitan.io/crm/v2/tenant/{tenant}/locations?page={page}&pageSize=2500', headers=headers)
        page += 1
        clients = response.json()['data']
        if response.json()['hasMore'] == False:
            moreClients = False
        result = saveClientList.delay(clients, company_id)
        delVariables([clients, response])
    
    # wait up to 30 seconds for the last task to complete
    count = 0
    while(result.status != 'SUCCESS' and count < 30):
        sleep(1)
        count += 1

    deleteExtraClients.delay(company_id, task_id)
    
    get_servicetitan_equipment.delay(company_id)
    doItAll.delay(company_id)

    frm = ""
    moreClients = True
    page = 0
    while(moreClients):
        page += 1
        response = requests.get(f'https://api.servicetitan.io/crm/v2/tenant/{tenant}/export/customers/contacts?from={frm}', headers=headers)
        # for number in response.json()['data']:
        #     numbers.append(number)
        numbers = response.json()['data']
        if response.json()['hasMore'] == True:
            frm = response.json()['continueFrom']
        else:
            moreClients = False        
        updateClientList.delay(numbers)
        delVariables([numbers, response])
    delVariables([frm, moreClients, headers, data, company, tenant])


@shared_task
def update_clients_with_last_service_date(equipment, company_id):
    company = Company.objects.get(id=company_id)
    client_dict = {}
    for equip in equipment:
        if equip['installedOn'] != None:
            try:
                client_dict[equip['customerId']] = datetime.strptime(equip['installedOn'], '%Y-%m-%dT%H:%M:%SZ').date() 
            except Exception as e:
                pass

    client_ids = client_dict.keys()

    # Use select_related to fetch related objects in a single query
    clients = Client.objects.filter(servTitanID__in=client_ids, company=company).select_related('company')

    # Use bulk_update to update multiple objects at once
    for client in clients:
        client.equipmentInstalledDate = Coalesce(client_dict.get(client.servTitanID), client.equipmentInstalledDate)
        client.save(update_fields=['equipmentInstalledDate'])

    # Return the number of clients updated
    return len(clients)

@shared_task
def get_servicetitan_equipment(company_id):
    company = Company.objects.get(id=company_id)
    tenant = company.tenantID
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = f'grant_type=client_credentials&client_id={company.clientID}&client_secret={company.clientSecret}'
    response = requests.post('https://auth.servicetitan.io/connect/token', headers=headers, data=data)    

    headers = {'Authorization': response.json()['access_token'], 'Content-Type': 'application/json', 'ST-App-Key': settings.ST_APP_KEY}
    moreEquipment = True
    #get client data
    page = 1
    while(moreEquipment):
        response = requests.get(f'https://api.servicetitan.io/equipmentsystems/v2/tenant/{tenant}/installed-equipment?page={page}&pageSize=2500', headers=headers)
        # additional option &modifiedOnOrAfter=2000-1-1T00:00:14-05:00
        page += 1
        equipment = response.json()['data']
        if response.json()['hasMore'] == False:
            moreEquipment = False
        # with open('equipment.json', 'a') as f:
        #     json.dump(equipment, f, indent=4)
        update_clients_with_last_service_date.delay(equipment, company_id)
        delVariables([equipment, response])
