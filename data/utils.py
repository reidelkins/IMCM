from time import sleep
from accounts.models import Company, CustomUser
from config import settings
from .models import Client, ZipCode, HomeListing, ScrapeResponse, ClientUpdate, Task, HomeListingTags

from bs4 import BeautifulSoup
from celery import shared_task
from datetime import datetime, timedelta
import gc
import json
import math
import requests
from scrapfly import ScrapeApiResponse, ScrapeConfig, ScrapflyClient
import traceback
from typing import List, Optional
from typing_extensions import TypedDict

from django.template.loader import get_template
from django.core.mail import EmailMessage, send_mail

scrapflies = []
for i in range(1, 21):
    scrapfly = ScrapflyClient( key=settings.SCRAPFLY_KEY, max_concurrency=1)
    scrapflies.append(scrapfly)

def delVariables(vars):
    for var in vars:
        try:
            del var
        except:
            pass
    gc.collect()

def findClientsToDelete(clientCount, subscriptionType):
    if subscriptionType == "Small Business":
        ceiling = 5000
    elif subscriptionType == "Franchise":
        ceiling = 10000
    elif subscriptionType == "Large Business":
        ceiling = 20000
    # elif subscriptionType == "Free Tier":
    #     ceiling = 100
    else:
        ceiling = 100000
    if clientCount > ceiling:
        return clientCount - ceiling
    else:
        return 0
    
@shared_task
def deleteExtraClients(companyID, taskID=None):
    company = Company.objects.get(id=companyID)
    clients = Client.objects.filter(company=company)
    deletedClients = findClientsToDelete(clients.count(), company.product.product.name)
    if deletedClients > 0:
        Client.objects.filter(id__in=list(clients.values_list('id', flat=True)[:deletedClients])).delete()
        admins = CustomUser.objects.filter(company=company, status="admin")
        mail_subject = "IMCM Clients Deleted"
        messagePlain = "Your company has exceeded the number of clients allowed for your subscription. The oldest clients have been deleted. You can upgrade your subscription at any time to increase the number of clients you can have."
        message = get_template("clientsDeleted.html").render({"deletedClients": deletedClients})
        for admin in admins:
            send_mail(subject=mail_subject, message=messagePlain, from_email=settings.EMAIL_HOST_USER, recipient_list=[admin.email], html_message=message, fail_silently=False)
    if taskID:
        task = Task.objects.get(id=taskID)
        task.deletedClients = deletedClients
        task.completed = True
        task.save()


def parseStreets(street):
    conversions = {"Alley": "Aly", "Avenue": "Ave", "Boulevard": "Blvd", "Circle": "Cir", "Court": "Crt", "Cove": "Cv", "Canyon": "Cnyn", "Drive": "Dr", "Expressway": "Expy", "Highway": "Hwy", 
        "Lane": "Ln", "Parkway": "Pkwy", "Place": "Pl", "Pike": "Pk", "Point": "Pt", "Road": "Rd", "Square": "Sq", "Street": "St", "Terrace": "Ter", "Trail": "Trl", "South": "S", "North": "N",
        "West": "W", "East": "E", "Northeast": "NE", "Northwest": "NW", "Southeast": "SE", "Southwest":"SW", "Ne": "NE", "Nw": "NW", "Sw":"SW", "Se":"SE" }
    for word in street.split():
        if word in conversions:
            street = street.replace(word, conversions[word])
    return street

def formatZip(zip):
    try:
        if type(zip) == float:
            zip = int(zip)
        if type(zip) == str:
            zip = zip.replace(' ', '')
            zip = (zip.split('-'))[0]
        if int(zip) > 500 and int(zip) < 99951:
            if len(zip) == 4:
                zip = '0' + str(zip)
            elif len(zip) == 3:
                zip = '00' + str(zip)
            elif len(zip) != 5:
                return False
        return zip
    except:
        return False

@shared_task
def saveClientList(clients, company_id, task=None):
    #create
    clientsToAdd = []
    company = Company.objects.get(id=company_id)        
    badStreets = ['none', 'null', 'na', 'n/a', 'tbd', '.', 'unk', 'unknown', 'no address listed', 'no address', 'cmo']
    for i in range(len(clients)):
        #service titan
        try:
            if 'active' in clients[i]:
                if clients[i]['active']:                    
                    street = parseStreets((str(clients[i]['address']['street'])).title())
                    if street.lower() in badStreets or 'tbd' in street.lower():
                        continue
                    zip = formatZip(clients[i]['address']['zip'])
                    if int(zip) < 500 or int(zip) > 99951:
                        continue
                    zipCode = ZipCode.objects.get_or_create(zipCode=str(zip))[0]                   
                    city=clients[i]['address']['city'],
                    city= city[0]            
                    state=clients[i]['address']['state']
                    name=clients[i]['name']
                    if clients[i]['address']['zip'] == None or not street or not zip or not city or not state or not name or zip == 0:
                        continue
                    clientsToAdd.append(Client(address=street, zipCode=zipCode, city=city, state=state, name=name, company=company, servTitanID=clients[i]['customerId']))                   
            #file upload
            else:
                street = parseStreets((str(clients[i]['address'])).title())
                if street.lower() in badStreets:
                        continue
                zip = formatZip(clients[i]['zip code'])
                zipCode = ZipCode.objects.get_or_create(zipCode=str(zip))[0]
                city = clients[i]['city']
                state = clients[i]['state']
                name = clients[i]['name']
                if 'phone number' in clients[i]:
                    phoneNumber = clients[i]['phone number']
                else:
                    phoneNumber = ""
                if clients[i]['zip code'] == None or not street or not zip or not city or not state or not name or zip == 0:
                        continue
                clientsToAdd.append(Client(address=street, zipCode=zipCode, city=city, state=state, name=name, company=company, phoneNumber=phoneNumber))
        except Exception as e:
            print("create error")
            print(e)
    Client.objects.bulk_create(clientsToAdd, ignore_conflicts=True)

    if task:
        deleteExtraClients.delay(company_id, task)
        doItAll.delay(company_id)
    delVariables([clientsToAdd, clients, company, company_id, badStreets])


@shared_task
def updateClientList(numbers):
    phoneNumbers = {}
    for number in numbers:
        try:
            phoneNumbers[number['customerId']] = number['phoneSettings']['phoneNumber']
        except:
            continue
    clients = Client.objects.filter(servTitanID__in=list(phoneNumbers.keys()))
    for client in clients:
        client.phoneNumber = phoneNumbers[client.servTitanID]
        client.save()
    delVariables([phoneNumbers, clients, numbers])


@shared_task
def getAllZipcodes(company):
    company_object = Company.objects.get(id=company)
    zipCode_objects = Client.objects.filter(company=company_object).values('zipCode')
    zipCodes = zipCode_objects.distinct()
    zipCodes = ZipCode.objects.filter(zipCode__in=zipCode_objects, lastUpdated__lt=(datetime.today()).strftime('%Y-%m-%d'))
    zips = list(zipCodes.order_by('zipCode').values('zipCode'))
    zipCodes.update(lastUpdated=datetime.today().strftime('%Y-%m-%d'))
    # zips = [{'zipCode': '37922'}]
    for i in range(len(zips) * 2):
    # for i in range(len(zips)):
        extra = ""
        if i % 2 == 0:
            status = "House For Sale"
            url = "https://www.realtor.com/realestateandhomes-search"
        elif i % 2 == 1:
            status = "House Recently Sold (6)"
            url = "https://www.realtor.com/realestateandhomes-search"
            extra = "show-recently-sold/"
        # elif i % 3 == 2:
        #     status = "For Rent"
        #     url = "https://www.realtor.com/apartments"
        find_data.delay(str(zips[i//2]['zipCode']), i, status, url, extra)
    delVariables([company_object, zipCode_objects, zipCodes, zips, company])

@shared_task
def find_data(zip, i, status, url, extra):
    scrapfly = scrapflies[i % 20]    
    try:
        first_page = f"{url}/{zip}/{extra}"
        first_result = scrapfly.scrape(ScrapeConfig(first_page, country="US", asp=False, proxy_pool="public_datacenter_pool"))        
        if first_result.status_code >= 400:
            scrapfly = scrapflies[i+5 % 20]
            first_result = scrapfly.scrape(ScrapeConfig(first_page, country="US", asp=False, proxy_pool="public_datacenter_pool"))
        content = first_result.scrape_result['content']
        soup = BeautifulSoup(content, features='html.parser')
        # resp = ScrapeResponse.objects.create(response=str(content), zip=zip, status=status, url=first_page)
        if "pg-1" not in first_result.context["url"]:
            url = first_result.context["url"] + "/pg-1"
        else:
            url = first_result.context["url"]
        first_data = parse_search(first_result, status)
        if not first_data:
            return
        if status == "For Rent":
            results = first_data["properties"]
            total = int(soup.find('div', {'data-testid': 'total-results'}).text)
            count = len(results)
            url += "/pg-1"
        else:
            results = first_data["results"]
            total = soup.find('span', {'class': 'result-count'}).text
            total = int(total.split(' ')[0])
            count = first_data["count"]
        # create_home_listings(results, status, resp.id)
        create_home_listings(results, status)
        if count == 0 or total == 0:
            return
        if count < 20: #I believe this can be 10
            total_pages = 1
        else:
            total_pages = math.ceil(total / count)
        for page in range(2, total_pages+1):
            assert "pg-1" in url  # make sure we don't accidently scrape duplicate pages
            page_url = url.replace("pg-1", f"pg-{page}")
            new_results = scrapfly.scrape(ScrapeConfig(url=page_url, country="US", asp=False, proxy_pool="public_datacenter_pool"))
            if first_result.status_code >= 400:
                scrapfly = scrapflies[i+5 % 20]
                new_results = scrapfly.scrape(ScrapeConfig(url=page_url, country="US", asp=False, proxy_pool="public_datacenter_pool"))
            content = new_results.scrape_result['content']
            # resp = ScrapeResponse.objects.create(response=str(content), zip=zip, status=status, url=page_url)
            parsed = parse_search(new_results, status)            
            if status == "For Rent":
                results = parsed["properties"]
            else:
                results = parsed["results"]
            # create_home_listings(results, status, resp.id)  
            create_home_listings(results, status)
    except Exception as e:
        print(f"ERROR during getHomesForSale: {e} with zipCode {zip}")
        print(f"URL: {url}")
    vars = [scrapfly, first_page, first_result, content, soup, first_data, results, total, count, url, extra, new_results, parsed]
    if total:
        vars.append(total)
    if page_url:
        vars.append(page_url)
    delVariables(vars)


class PropertyPreviewResult(TypedDict):
    property_id: str
    listing_id: str
    permalink: str
    list_price: int
    price_reduces_amount: Optional[int]
    description: dict
    location: dict
    photos: List[dict]
    list_date: str
    last_update_date: str
    tags: List[str]

class SearchResults(TypedDict):
    count: int
    total: int
    results: List[PropertyPreviewResult]

def parse_search(result: ScrapeApiResponse, searchType: str) -> SearchResults:
    data = result.selector.css("script#__NEXT_DATA__::text").get()
    if not data:
        print(f"page {result.context['url']} is not a property listing page")
        return
    
    data = dict(json.loads(data))
    try:
        if(searchType == "For Rent"):
            data = data["props"]["pageProps"]
        else:
            data = data["props"]["pageProps"]["searchResults"]["home_search"]
        return data
    except KeyError:
        print(f"page {result.context['url']} is not a property listing page")
        return False

def create_home_listings(results, status, resp=None):
    two_years_ago = datetime.now() - timedelta(days=365*2)
    for listing in results:
        zip_object, created = ZipCode.objects.get_or_create(zipCode = listing['location']['address']['postal_code'])
        try:
            if status == "House Recently Sold (6)":
                listType = listing["last_update_date"]
                if listType != None:
                    try:
                        dateCompare = datetime.strptime(listType, "%Y-%m-%dT%H:%M:%SZ")
                    except:
                        dateCompare = datetime.strptime(listType, "%Y-%m-%d")
                    if dateCompare < two_years_ago:
                        continue
                else:
                    listType = listing["description"]["sold_date"]
                    if listType != None:
                        try:
                            dateCompare = datetime.strptime(listType, "%Y-%m-%dT%H:%M:%SZ")
                        except:
                            dateCompare = datetime.strptime(listType, "%Y-%m-%d")
                        if dateCompare < two_years_ago:
                            continue

            else:
                listType = listing["list_date"]
            if listType == None:
                listType = "2022-01-01"
            if listing['list_price']:
                price = listing['list_price']
            elif listing['description']['sold_price']:
                price = listing['description']['sold_price']
            else:
                price = 0
            if listing['description']['year_built']:
                year_built = listing['description']['year_built']
            else:
                year_built = 0
            homeListing = HomeListing.objects.get_or_create(
                        zipCode= zip_object,
                        address= parseStreets((listing['location']['address']['line']).title()),
                        status= status,
                        listed= listType[:10],
                        price = price,
                        housingType = listing['description']['type'],
                        year_built = year_built,
                        )
            if resp:
                homeListing[0].ScrapeResponse = ScrapeResponse.objects.get(id=resp)
                homeListing[0].save()
            if listing["tags"]:
                for tag in listing["tags"]:
                    currTag = HomeListingTags.objects.get_or_create(tag=tag)
                    homeListing[0].tag.add(currTag[0])


        except Exception as e: 
            print(f"ERROR for Single Listing: {e} with zipCode {zip_object}.")
            print(traceback.format_exc())
    delVariables([zip_object, created, listType, homeListing, currTag, results])

@shared_task
def updateStatus(zip, company, status):
    company = Company.objects.get(id=company)
    try:
        zipCode_object = ZipCode.objects.get(zipCode=zip)
    except Exception as e:
        print(f"ERROR during updateStatus: {e} with zipCode {zip}")
        return
    #addresses from all home listings with the provided zip code and status
    listedAddresses = HomeListing.objects.filter(zipCode=zipCode_object, status=status).values('address')
    clientsToUpdate = Client.objects.filter(company=company, address__in=listedAddresses, zipCode=zipCode_object)
    previousListed = Client.objects.filter(company=company, zipCode=zipCode_object, status=status)
    newlyListed = clientsToUpdate.difference(previousListed)
    #TODO add logic so if date for one listing is older than date of other, it will not update status
    for toList in newlyListed:
        existingUpdates = ClientUpdate.objects.filter(client=toList, status__in=["House For Sale", "House Recently Sold (6)"])
        update = True
        try:
            for listing in existingUpdates:
                if listing.listed > HomeListing.objects.filter(address=toList.address, status=status)[0].listed:
                    update = False
        except Exception as e:
            print(e)
        if update:
            homeListing = HomeListing.objects.get(address=toList.address, status=status)
            toList.status = status
            toList.price = homeListing.price
            toList.year_built = homeListing.year_built
            toList.housingType = homeListing.housingType
            toList.save()
            for tag in homeListing.tag.all():
                toList.tag.add(tag)
        try:
            listing = HomeListing.objects.filter(zipCode=zipCode_object, address=toList.address, status=status)
            ClientUpdate.objects.get_or_create(client=toList, status=status, listed=listing[0].listed)
        except Exception as e:
            print("Cant find listing to list")
            print("This should not be the case")
    # TODO There is an issue where clients uploaded with wrong zip code and are being marked to be unlisted when they should not be
    # unlisted = previousListed.difference(clientsToUpdate)
    # for toUnlist in unlisted:
    #     toUnlist.status = "Taken Off Market"
    #     toUnlist.save()
    #     ClientUpdate.objects.create(client=toUnlist, status="Taken Off Market")


    clientsToUpdate = list(clientsToUpdate.values_list('servTitanID', flat=True))
    for client in clientsToUpdate:
        if client is None:
            clientsToUpdate.remove(client)
    
    if clientsToUpdate:
        update_serviceTitan_client_tags.delay(clientsToUpdate, company.id, status)
    delVariables([zipCode_object, listedAddresses, clientsToUpdate, previousListed, newlyListed, toList, listing, clientsToUpdate])


@shared_task
def update_clients_statuses(company_id=None):
    if company_id:
        companies = Company.objects.filter(id=company_id)
    else:
        companies = Company.objects.all()
    for company in companies:
        try:
            if company.product.id != "price_1MhxfPAkLES5P4qQbu8O45xy":
                zipCode_objects = Client.objects.filter(company=company).values('zipCode')
                zipCodes = zipCode_objects.distinct()
                zips = list(zipCodes.order_by('zipCode').values('zipCode'))
                for zip in zips:
                    zip = zip['zipCode']
                    updateStatus.delay(zip, company.id, "House For Sale")
                for zip in zips:
                    zip = zip['zipCode']
                    updateStatus.delay(zip, company.id, "House Recently Sold (6)")
        except Exception as e:
            print(f"ERROR during update_clients_statuses: {e} with company {company}")
            print(traceback.format_exc())
                
    delVariables([companies, company, zipCode_objects, zipCodes, zips, zip])
                 

@shared_task
def sendDailyEmail(company_id=None):
    if company_id:
        companies = Company.objects.filter(id=company_id)
    else:
        companies = Company.objects.all()
    for company in companies:
        try:
            if company.product.id != "price_1MhxfPAkLES5P4qQbu8O45xy":
                emails = list(CustomUser.objects.filter(company=company).values_list('email'))
                subject = 'Did Your Customers Move?'
                
                forSaleCustomers = Client.objects.filter(company=company, status="House For Sale").exclude(contacted=True).count()
                soldCustomers = Client.objects.filter(company=company, status="House Recently Sold (6)").exclude(contacted=True).count()
                message = get_template("dailyEmail.html").render({
                    'forSale': forSaleCustomers, 'sold': soldCustomers
                })
                
                if soldCustomers > 0 or forSaleCustomers > 0:
                    for email in emails:
                        email = email[0]
                        msg = EmailMessage(
                            subject,
                            message,
                            settings.EMAIL_HOST_USER,
                            [email]
                        )
                        msg.content_subtype ="html"
                        msg.send()
        except Exception as e:
            print(f"ERROR during sendDailyEmail: {e} with company {company}")
            print(traceback.format_exc())
    # if not company_id:
    #     HomeListing.objects.all().delete()
    ZipCode.objects.filter(lastUpdated__lt = datetime.today() - timedelta(days=3)).delete()
    delVariables([companies, company, emails, subject, forSaleCustomers, soldCustomers, message, email, msg])


@shared_task
def auto_update(company_id=None):
    if company_id:
        try:
            company = Company.objects.get(id=company_id)
            getAllZipcodes(company_id)

        except:
            print("Company does not exist")
            return
    else:
        companies = Company.objects.all()
        for company in companies:
            try:
                if company.product.id != "price_1MhxfPAkLES5P4qQbu8O45xy":
                    getAllZipcodes(company.id)
                else:
                    print("free tier")
            except Exception as e:
                print(e)
    delVariables([company, companies])
    

@shared_task
def update_serviceTitan_client_tags(forSale, company, status):
    try:
        company = Company.objects.get(id=company)
        if forSale and (company.serviceTitanForSaleTagID or company.serviceTitanRecentlySoldTagID):
            print(forSale)
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            data = f'grant_type=client_credentials&client_id={company.clientID}&client_secret={company.clientSecret}'
            response = requests.post('https://auth.servicetitan.io/connect/token', headers=headers, data=data)
            headers = {'Authorization': response.json()['access_token'], 'Content-Type': 'application/json', 'ST-App-Key': settings.ST_APP_KEY}
            if status == 'House For Sale':
                tagType = [str(company.serviceTitanForSaleTagID)]
            elif status == 'House Recently Sold (6)':
                forSaleToRemove = forSale
                tagType = [str(company.serviceTitanRecentlySoldTagID)]
                payload={'customerIds': forSaleToRemove, 'tagTypeIds': [str(company.serviceTitanForSaleTagID)]}
                response = requests.delete(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
                if response.status_code != 200:
                    resp = response.json()
                    error = resp['title']
                    error = error.replace('(', "").replace(')', "").replace(',', " ").replace(".", "").split()
                    for word in error:
                        if word.isdigit():
                            # Client.objects.filter(servTitanID=word).delete()
                            word = int(word)
                            if word in forSaleToRemove:
                                forSaleToRemove.remove(word)
                    payload={'customerIds': forSaleToRemove, 'tagTypeIds': tagType}
                    response = requests.delete(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
                    print(response.status_code)
                    if response.status_code != 200:
                        print(response.json())
            payload={'customerIds': forSale, 'tagTypeIds': tagType}
            response = requests.put(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
            if response.status_code != 200:
                resp = response.json()
                error = resp['title']
                error = error.replace('(', "").replace(')', "").replace(',', " ").replace(".", "").split()
                for word in error:
                    if word.isdigit():
                        # Client.objects.filter(servTitanID=word).delete()
                        word = int(word)
                        if word in forSale:
                            forSale.remove(word)
                if status == 'House Recently Sold (6)':
                    payload={'customerIds': forSale, 'tagTypeIds': [str(company.serviceTitanForSaleTagID)]}
                    response = requests.delete(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
                payload={'customerIds': forSale, 'tagTypeIds': tagType}
                response = requests.put(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
    except Exception as e:
        print("updating service titan clients failed")
        print(f"ERROR: {e}")
        print(traceback.format_exc())
    delVariables([headers, data, response, payload, company, status, tagType, forSale, resp, error, word])


@shared_task
def remove_all_serviceTitan_tags(company):
    try:
        company = Company.objects.get(id=company)
        if company.serviceTitanForSaleTagID or company.serviceTitanRecentlySoldTagID:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            data = f'grant_type=client_credentials&client_id={company.clientID}&client_secret={company.clientSecret}'
            response = requests.post('https://auth.servicetitan.io/connect/token', headers=headers, data=data)
            headers = {'Authorization': response.json()['access_token'], 'Content-Type': 'application/json', 'ST-App-Key': settings.ST_APP_KEY}
            time = datetime.now()
            tagTypes = [[str(company.serviceTitanForSaleTagID)], [str(company.serviceTitanRecentlySoldTagID)]]
            for tag in tagTypes:
                # get a list of all the servTitanIDs for the clients with one from this company
                # clients = list(Client.objects.filter(company=company).values_list('servTitanID'))
                clients = list(Client.objects.filter(company=company).exclude(servTitanID=None).values_list('servTitanID', flat=True))
                iters = (len(clients) // 250) + 1
                for i in range(iters):
                    if time < datetime.now()-timedelta(minutes=15):
                        headers = {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        }
                        data = f'grant_type=client_credentials&client_id={company.clientID}&client_secret={company.clientSecret}'
                        response = requests.post('https://auth.servicetitan.io/connect/token', headers=headers, data=data)
                        headers = {'Authorization': response.json()['access_token'], 'Content-Type': 'application/json', 'ST-App-Key': settings.ST_APP_KEY}
                        time = datetime.now()
                    print(i)
                    x = clients[i*250:(i+1)*250]
                    payload={'customerIds': x, 'tagTypeIds': tag}
                    response = requests.delete(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
                    if response.status_code != 200:
                        resp = response.json()
                        error = resp['title']
                        error = error.replace('(', "").replace(')', "").replace(',', " ").replace(".", "")
                        error = error.split()
                        for word in error:
                            if word.isdigit():
                                word = int(word)
                                # Client.objects.filter(servTitanID=word).delete()
                                if word in x:
                                    x.remove(word)
                        if x:
                            payload={'customerIds': x, 'tagTypeIds': tag}
                            response = requests.delete(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tags', headers=headers, json=payload)
                            print(x)
                            print(response.status_code)
                            if response.status_code != 200:
                                print(response.json())
                        else:
                            print("no clients to remove")
            Client.objects.filter(company=company).update(status="No Change")
                    
                    
                
    except Exception as e:
        print("updating service titan clients failed")
        print(f"ERROR: {e}")
        print(traceback.format_exc())


def update_serviceTitan_tasks(clients, company, status):
    if clients and (company.serviceTitanForSaleTagID or company.serviceTitanRecentlySoldTagID):
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            data = f'grant_type=client_credentials&client_id={company.clientID}&client_secret={company.clientSecret}'
            response = requests.post('https://auth.servicetitan.io/connect/token', headers=headers, data=data)
            headers = {'Authorization': response.json()['access_token'], 'Content-Type': 'application/json', 'ST-App-Key': settings.ST_APP_KEY}
            response = requests.get(f'https://api.servicetitan.io/taskmanagement/v2/tenant/{str(company.tenantID)}/data', headers=headers)
            with open('tasks.json', 'w') as f:
                json.dump(response.json(), f)
            # if response.status_code != 200:
            #     resp = response.json()
            #     error = resp['errors'][''][0]
            #     error = error.replace('(', "").replace(')', "").replace(',', " ").replace(".", "").split()
            #     for word in error:
            #         if word.isdigit():
            #             Client.objects.filter(servTitanID=word).delete()
            #             forSale.remove(word)
            #     payload={'customerIds': forSale, 'taskTypeId': str(company.serviceTitanTaskID)}
            #     response = requests.put(f'https://api.servicetitan.io/crm/v2/tenant/{str(company.tenantID)}/tasks', headers=headers, json=payload)
        except Exception as e:
            print("updating service titan tasks failed")
            print(f"ERROR: {e}")
            print(traceback.format_exc())
    delVariables([headers, data, response, company, status])


# send email to every customuser with the html file that has the same name as the template
def send_update_email(templateName):
    try:
        users = list(CustomUser.objects.filter(isVerified=True).values_list('email', flat=True))
        mail_subject = "Is My Customer Moving Product Updates"
        messagePlain = "Thank you for signing up for Is My Customer Moving. We have some updates for you. Please visit https://app.ismycustomermoving.com/ to see them."        
        message = get_template(f"{templateName}.html").render()
        for user in users:            
            send_mail(subject=mail_subject, message=messagePlain, from_email=settings.EMAIL_HOST_USER, recipient_list=[user], html_message=message, fail_silently=False)
    except Exception as e:
        print("sending update email failed")
        print(f"ERROR: {e}")
        print(traceback.format_exc())

@shared_task(rate_limit='1/s')
def doItAll(company):
    try:
        company = Company.objects.get(id=company)
        result = auto_update.delay(company.id)  # Schedule auto_update task
        sleep(3600)  # TODO Calculate ETA for update_clients_statuses task
        result = update_clients_statuses(company.id)  # Schedule update_clients_statuses task
        sleep(360)
        result.then(sendDailyEmail.apply_async, args=[company.id])
    except Exception as e:
        print("doItAll failed")
        print(f"ERROR: {e}")
        print(traceback.format_exc())
