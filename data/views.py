from rest_framework.permissions import IsAuthenticated
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

import datetime
import requests

from accounts.models import CustomUser, Company
from accounts.serializers import UserSerializerWithToken
from config import settings
from .models import Client, ClientUpdate, HomeListing, Task, HomeListingTags
from .serializers import ClientListSerializer, HomeListingSerializer
from .syncClients import get_fieldEdge_clients, get_hubspot_clients, get_salesforce_clients, get_serviceTitan_clients
from .utils import getAllZipcodes, saveClientList, doItAll

# Create your views here.
class AllClientListView(generics.ListAPIView):
    serializer_class = ClientListSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        user = CustomUser.objects.get(id=self.request.user.id)
        return Client.objects.filter(company=user.company).order_by('status')

class CustomPagination(PageNumberPagination):
    page_size = 1000

class ClientListView(generics.ListAPIView):
    serializer_class = ClientListSerializer
    pagination_class = CustomPagination
    
    def get_queryset(self):
        user = CustomUser.objects.get(id=self.kwargs['user'])
        query_params = self.request.query_params

        # Initialize the queryset with the base filters
        queryset = Client.objects.prefetch_related('clientUpdates_client').filter(company=user.company)

        if 'min_price' in query_params:
            queryset = queryset.filter(price__gte=query_params['min_price'])
        if 'max_price' in query_params:
            queryset = queryset.filter(price__lte=query_params['max_price'], price__gt=0)
        if 'min_year' in query_params:
            queryset = queryset.filter(year_built__gte=query_params['min_year'])
        if 'max_year' in query_params:
            queryset = queryset.filter(year_built__lte=query_params['max_year'], year_built__gt=0)
        if 'status' in query_params:
            statuses = []
            if "For Sale" in query_params['status']:
                statuses.append("House For Sale")
            if "Recently Sold" in query_params['status']:
                statuses.append("House Recently Sold (6)")
            queryset = queryset.filter(status__in=statuses)
        if 'equip_install_date_min' in query_params:
            queryset = queryset.filter(equipmentInstalledDate__gte=query_params['equip_install_date_min'])
        if 'equip_install_date_max' in query_params:
            queryset = queryset.filter(equipmentInstalledDate__lte=query_params['equip_install_date_max'])
        #TODO
        # if 'tags' in query_params:
        #     tags = [tag.replace('[', '').replace(']', '').replace(' ', '_') for tag in query_params.get('tags', '').split(',')]
        #     queryset = queryset.filter(tag__tag__in=tags)
        if user.company.product.id == "price_1MhxfPAkLES5P4qQbu8O45xy":
            queryset = queryset.order_by('name')
        elif user.status == 'admin':
            queryset = queryset.order_by('status')
        else:
            queryset = queryset.exclude(status='No Change').order_by('status')
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        user = CustomUser.objects.get(id=self.kwargs['user'])
        allClients = Client.objects.filter(company=user.company)
        forSale = allClients.filter(status="House For Sale", contacted=False).count()
        recentlySold = allClients.filter(status="House Recently Sold (6)", contacted=False).count()
        allClientUpdates = ClientUpdate.objects.filter(client__company=user.company)
        forSaleAllTime = allClientUpdates.filter(status="House For Sale").count()
        recentlySoldAllTime = allClientUpdates.filter(status="House Recently Sold (6)").count()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            clients = serializer.data
            return self.get_paginated_response({"forSale": forSale, "forSaleAllTime": forSaleAllTime, "recentlySoldAllTime": recentlySoldAllTime, "recentlySold": recentlySold, "clients": clients})

        serializer = self.get_serializer(queryset, many=True)
        return Response({"forSale": forSale, "forSaleAllTime": forSaleAllTime, "recentlySoldAllTime": recentlySoldAllTime, "recentlySold": recentlySold, "clients": clients})

class FilteredClientListView(generics.ListAPIView):
    serializer_class = ClientListSerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        user = CustomUser.objects.get(id=self.kwargs['user'])
        if user.company.product.id == "price_1MhxfPAkLES5P4qQbu8O45xy":
            return Client.objects.prefetch_related('clientUpdates_client').filter(company=user.company).order_by('name')
        elif user.status == 'admin':
            return Client.objects.prefetch_related('clientUpdates_client').filter(company=user.company).order_by('status')
        else:
            return Client.objects.prefetch_related('clientUpdates_client').filter(company=user.company).exclude(status='No Change').order_by('status')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        user = CustomUser.objects.get(id=self.kwargs['user'])
        allClients = Client.objects.filter(company=user.company)
        if user.company.product.id == "price_1MhxfPAkLES5P4qQbu8O45xy":
            page = self.paginate_queryset(queryset)
        


class RecentlySoldView(generics.ListAPIView):
    serializer_class = HomeListingSerializer
    pagination_class = CustomPagination
    def get_queryset(self):
        company = Company.objects.get(id=self.kwargs['company'])
        if company.recentlySoldPurchased:
            zipCode_objects = Client.objects.filter(company=company).values('zipCode')            
            queryset = HomeListing.objects.filter(zipCode__in=zipCode_objects, listed__gt=(datetime.datetime.today()-datetime.timedelta(days=30)).strftime('%Y-%m-%d')).order_by('listed')
            query_params = self.request.query_params
            if 'min_price' in query_params:
                queryset = queryset.filter(price__gte=query_params['min_price'])
            if 'max_price' in query_params:
                queryset = queryset.filter(price__lte=query_params['max_price'], price__gt=0)
            if 'min_year' in query_params:
                queryset = queryset.filter(year_built__gte=query_params['min_year'])
            if 'max_year' in query_params:
                queryset = queryset.filter(year_built__lte=query_params['max_year'], year_built__gt=0)
            if 'min_days_ago' in query_params:
                queryset = queryset.filter(listed__lt=(datetime.datetime.today()-datetime.timedelta(days=int(query_params['min_days_ago']))).strftime('%Y-%m-%d'))
            if 'max_days_ago' in query_params:
                queryset = queryset.filter(listed__gt=(datetime.datetime.today()-datetime.timedelta(days=int(query_params['max_days_ago']))).strftime('%Y-%m-%d'))
            return queryset
        else:
            return HomeListing.objects.none()

class AllRecentlySoldView(generics.ListAPIView):
    serializer_class = HomeListingSerializer
    def get_queryset(self):
        company = Company.objects.get(id=self.kwargs['company'])
        if company.recentlySoldPurchased:
            zipCode_objects = Client.objects.filter(company=company).values('zipCode')            
            return HomeListing.objects.filter(zipCode__in=zipCode_objects, listed__gt=(datetime.datetime.today()-datetime.timedelta(days=30)).strftime('%Y-%m-%d')).order_by('listed')
        else:
            return HomeListing.objects.none()

class UpdateStatusView(APIView):
    def get(self, request, *args, **kwargs):
        try:
            getAllZipcodes.delay(self.kwargs['company'])
        except Exception as e:
            print(f"ERROR: Update Status View: {e}")
        return Response("", status=status.HTTP_201_CREATED, headers="")

class ClientListAndUpdatesView(generics.ListAPIView):
    serializer_class = ClientListSerializer
    pagination_class = CustomPagination
    def get_queryset(self):
        company = Company.objects.get(id=self.kwargs['company'])
        print(Client.objects.filter(company=company).count())
        return Client.objects.prefetch_related('clientUpdates').filter(company=company).order_by('status')

class UploadFileView(generics.ListAPIView):
    def get(self, request, *args, **kwargs):
        try:
            try:
                task = Task.objects.get(id=self.kwargs['company'])
                if task.completed:
                    deleted = task.deletedClients
                    # task.delete()
                    return Response({"status": "SUCCESS", "data": "Clients Uploaded! Come back in about an hour to see your results.", "deleted": deleted}, status=status.HTTP_201_CREATED, headers="")
                else:
                    return Response({"status": "UNFINISHED", "clients": []}, status=status.HTTP_201_CREATED)
            except Exception as e:
                print(e)
                return Response({"status": "Task Error"}, status=status.HTTP_400_BAD_REQUEST)          
        except Exception as e:
            print(e)
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)
        
    def put(self, request, *args, **kwargs):
        company_id = self.kwargs['company']
        try:
            company = Company.objects.get(id=company_id)
        except Exception as e:
            print(e)
            return Response({"status": "Company Error"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            task = Task.objects.create()            
            saveClientList.delay(request.data, company_id, task=task.id)
        except Exception as e:
            print(e)
            return Response({"status": "File Error"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"data": "Clients Uploaded! Come back in about an hour to see your results", "task": task.id}, status=status.HTTP_201_CREATED, headers="")

# create a class for update client that will be used for the put and delete requests
class UpdateClientView(APIView):
    def put(self, request, *args, **kwargs):
        try:
            client = Client.objects.get(id=request.data['clients'])
            if request.data['note']:
                client.note = request.data['note']
                ClientUpdate.objects.create(client=client, note=request.data['note'])
            if request.data['contacted'] != "":
                client.contacted = request.data['contacted']
                ClientUpdate.objects.create(client=client, contacted=request.data['contacted'])
            client.save()
        except Exception as e:
            print(e)
            return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "Client Updated"}, status=status.HTTP_201_CREATED, headers="")

    def delete(self, request, *args, **kwargs):
        try:
            if len(request.data['clients']) == 1:
                client = Client.objects.get(id=request.data['clients'][0])
                client.delete()
            else:
                for client in request.data['clients']:
                    client = Client.objects.get(id=client)
                    client.delete()
        except Exception as e:
            print(e)
            return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "Client Deleted"}, status=status.HTTP_201_CREATED, headers="")

class ServiceTitanView(APIView):
    def get(self, request, *args, **kwargs):
        try:
            try:
                task = Task.objects.get(id=self.kwargs['company'])
                if task.completed:
                    deleted = task.deletedClients
                    # task.delete()
                    return Response({"status": "SUCCESS", "data": "Clients Synced! Come back in about an hour to see your results.", "deleted": deleted}, status=status.HTTP_201_CREATED, headers="")
                else:
                    # clients = Company.objects.get(id="faee8ca7-e5de-4c60-8578-0ac6bc576930").client_set.all()
                    # if clients.count() > 0:
                    #     return Response({"status": "UNFINISHED", "clients": ClientListSerializer(clients[:1000], many=True).data}, status=status.HTTP_201_CREATED)
                    return Response({"status": "UNFINISHED", "clients": []}, status=status.HTTP_201_CREATED)
            except Exception as e:
                print(e)
                return Response({"status": "Task Error"}, status=status.HTTP_400_BAD_REQUEST)          
        except Exception as e:
            print(e)
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)
    def put(self, request, *args, **kwargs):
        try:
            company_id = self.kwargs['company']
            try:
                Company.objects.get(id=company_id)
                task = Task.objects.create() 
                get_serviceTitan_clients.delay(company_id, task.id)                          
                return Response({"status": "Success", "task": task.id}, status=status.HTTP_201_CREATED, headers="")
            except Exception as e:
                print(e)
                return Response({"status": "Company Error"}, status=status.HTTP_400_BAD_REQUEST)            
        except Exception as e:
            print(e)
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)

class SalesforceConsumerView(APIView):
    # GET request that returns the Salesforce Consumer Key and Consumer Secret from the config file, make this protected
    # permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            return Response({"consumer_key": settings.SALESFORCE_CONSUMER_KEY, "consumer_secret": settings.SALESFORCE_CONSUMER_SECRET}, status=status.HTTP_201_CREATED, headers="")
        except Exception as e:
            print(e)
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, *args, **kwargs):
        try:
            company_id = self.kwargs['company']
            try:
                company = Company.objects.get(id=company_id)
                company.crm = "Salesforce"
                code = request.data['code']
                headers = {
                    'Content-type': 'application/x-www-form-urlencoded',
                }

                # Make the request
                response = requests.post(f'https://login.salesforce.com/services/oauth2/token?grant_type=authorization_code&client_id={settings.SALESFORCE_CONSUMER_KEY}&client_secret={settings.SALESFORCE_CONSUMER_SECRET}&redirect_uri=http://localhost:3000/dashboard/settings&code={code}', headers=headers)

                # Parse the response
                response_data = response.json()
                new_access_token = response_data['access_token']
                new_refresh_token = response_data['refresh_token']
                company.sfAccessToken = new_access_token
                company.sfRefreshToken = new_refresh_token
                company.save()
                user = CustomUser.objects.get(id=request.data['id'])
                serializer = UserSerializerWithToken(user, many=False)
                return Response(serializer.data)
            except Exception as e:
                print(e)
                return Response({"status": "Company Error"}, status=status.HTTP_400_BAD_REQUEST)            
        except Exception as e:
            print(e)
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        try:
            company_id = self.kwargs['company']
            
            try:
                get_salesforce_clients(company_id)
                return Response({"status": "Success"}, status=status.HTTP_201_CREATED, headers="")
            except Exception as e:
                print(e)
                return Response({"status": "Company Error"}, status=status.HTTP_400_BAD_REQUEST)            
        except Exception as e:
            print(e)
            return Response({"status": "error"}, status=status.HTTP_400_BAD_REQUEST)
        
# @api_view(['PUT', 'DELETE'])
# def update_client(request):
#     try:
#         if request.method == 'PUT':
#             try:
#                 client = Client.objects.get(id=request.data['clients'])
#                 if request.data['note']:
#                     client.note = request.data['note']
#                     ClientUpdate.objects.create(client=client, note=request.data['note'])
#                 if request.data['contacted'] != "":
#                     client.contacted = request.data['contacted']
#                     ClientUpdate.objects.create(client=client, contacted=request.data['contacted'])
#                 client.save()
#             except Exception as e:
#                 print(e)
#                 return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
#         elif request.method == 'DELETE':
#             try:
#                 if len(request.data['clients']) == 1:
#                     client = Client.objects.get(id=request.data['clients'][0])
#                     client.delete()
#                 else:
#                     Client.objects.filter(id__in=request.data['clients']).delete()
#             except Exception as e:
#                 print(e)
#                 return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)
#         return Response({"status": "Success"}, status=status.HTTP_201_CREATED, headers="")
#     except Exception as e:
#         print(e)
#         return Response({"status": "Data Error"}, status=status.HTTP_400_BAD_REQUEST)