from django.db import models
from django.core.exceptions import ValidationError
import uuid
from datetime import datetime, timedelta


# from accounts.models import Company
STATUS = [
    ('House For Sale','House For Sale'),
    ('House For Rent','House For Rent'),
    ('House Recently Sold (6)','House Recently Sold (6)'),
    ('Recently Sold (12)','Recently Sold (12)'),
    ('Taken Off Market', 'Taken Off Market'),
    ('No Change', 'No Change')
]

def zipTime():
    return (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

class ZipCode(models.Model):
    zipCode = models.CharField(max_length=5, primary_key=True, unique=True)
    lastUpdated = models.DateField(default=zipTime)

class Client(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    zipCode = models.ForeignKey(ZipCode, on_delete=models.SET_NULL, blank=True, null=True,  related_name='client_zipCode')
    company = models.ForeignKey("accounts.Company", blank=True, null=True, on_delete=models.SET_NULL, related_name='client_company')
    status = models.CharField(max_length=25, choices=STATUS, default='No Change')
    city = models.CharField(max_length=40, blank=True, null=True)
    state = models.CharField(max_length=31, blank=True, null=True)
    contacted = models.BooleanField(default=False)
    note = models.TextField(default="", blank=True, null=True)
    servTitanID = models.IntegerField(blank=True, null=True)
    phoneNumber = models.CharField(max_length=100, blank=True, null=True)
    price = models.IntegerField(default=0, blank=True, null=True)
    housingType = models.CharField(max_length=100, default=" ", blank=True, null=True)
    year_built = models.IntegerField(default=0, blank=True, null=True)
    tag = models.ManyToManyField("HomeListingTags", blank=True, related_name='client_tags')
    equipmentInstalledDate = models.DateField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'name', 'address')

def formatToday():
    return datetime.today().strftime('%Y-%m-%d')

class ClientUpdate(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='clientUpdates_client')
    date = models.DateField(default=formatToday)
    status = models.CharField(max_length=25, choices=STATUS, default='No Change', blank=True, null=True)
    listed = models.CharField(max_length=30, blank=True, null=True)
    note = models.TextField(default="", blank=True, null=True)
    contacted = models.BooleanField(blank=True, null=True)

class ScrapeResponse(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    date = models.DateField(default=formatToday)
    response = models.TextField(default="")
    zip = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=25, choices=STATUS, default='No Change', blank=True, null=True)
    url = models.CharField(max_length=100, blank=True, null=True)

class HomeListing(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    zipCode = models.ForeignKey(ZipCode, blank=True, null=True, on_delete=models.SET_NULL, related_name='homeListing_zipCode')
    address = models.CharField(max_length=100)
    status = models.CharField(max_length=25, choices=STATUS, default='Off Market')
    listed = models.CharField(max_length=30, default=" ")
    ScrapeResponse = models.ForeignKey(ScrapeResponse, blank=True, null=True, on_delete=models.SET_NULL, related_name='homeListing_ScrapeResponse')
    price = models.IntegerField(default=0)
    housingType = models.CharField(max_length=100, default=" ")
    year_built = models.IntegerField(default=0)
    tag = models.ManyToManyField("HomeListingTags", blank=True, related_name='homeListing_tag')
    
class HomeListingTags(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    tag = models.CharField(max_length=100)

    def __str__(self):
        return self.tag


class Task(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    completed = models.BooleanField(default=False)
    deletedClients = models.IntegerField(default=0)

class Referral(models.Model):
    id = models.UUIDField(primary_key=True, unique=True,
                          default=uuid.uuid4, editable=False)
    franchise = models.ForeignKey("accounts.Franchise", on_delete=models.CASCADE)
    referredFrom = models.ForeignKey("accounts.Company", on_delete=models.SET_NULL, related_name='referredFrom', blank=True, null=True)
    referredTo = models.ForeignKey("accounts.Company", on_delete=models.SET_NULL, related_name='referredTo', blank=True, null=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='referralClient', blank=True, null=True)
    contacted = models.BooleanField(default=False)

    # on save, make sure both the referredFrom and referredTo are not the same and they are part of the franchise
    def save(self, *args, **kwargs):
        if self.referredFrom == self.referredTo:
            raise ValidationError("Referred From and Referred To cannot be the same")
        if self.referredFrom.franchise != self.franchise or self.referredTo.franchise != self.franchise:
            raise ValidationError("Both Referred From and Referred To must be part of the franchise")
        if self.client.company.franchise != self.franchise:
            raise ValidationError("Client must be part of the franchise")
        if self.client.company != self.referredFrom:
            raise ValidationError("Client must have the same company as Referred From")
            
        super(Referral, self).save(*args, **kwargs)