from django.core.mail import send_mail, EmailMultiAlternatives, send_mass_mail, EmailMessage
from django.db import models
from django.contrib.auth.models import User, AbstractUser
from django.conf import settings

from django.template.loader import render_to_string
from django.utils import timezone

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django_ckeditor_5.fields import CKEditor5Field
from datetime import datetime, timedelta
import json
PURCHASE_REQUEST_STATUS = (
    ('draft', 'Draft'),
    ('approved', 'Approved'),
    ('submitted', 'Submitted'),
    ('rejected', 'Rejected'),
)

RFQ_STATUS = (
    ('selected', 'Vendor Selected'),
    ('awaiting', 'Awaiting Vendor Selection'),
    ('cancelled', 'Cancelled'),
)

PURCHASE_ORDER_STATUS = (
    ('draft', 'Draft'),
    ('awaiting', 'Awaiting Goods'),
    ('completed', 'Order Completed'),
    ('cancelled', 'Cancelled'),
)

PRODUCT_TYPE = (
    ('consumable', 'Consumable'),
    ('store-able', 'Store-able'),
    ('services', 'Services'),
)


# For RFQs
class SelectedVendorManager(models.Manager):
    def get_queryset(self):
        return super(SelectedVendorManager, self).get_queryset().filter(status='selected')


class AwaitingVendorManager(models.Manager):
    def get_queryset(self):
        return super(AwaitingVendorManager, self).get_queryset().filter(status='awaiting')


class CancelledVendorManager(models.Manager):
    def get_queryset(self):
        return super(CancelledVendorManager, self).get_queryset().filter(status='cancelled')


# For Purchase Requests
class DraftPRManager(models.Manager):
    def get_queryset(self):
        return super(DraftPRManager, self).get_queryset().filter(status='draft')


class ApprovedPRManager(models.Manager):
    def get_queryset(self):
        return super(ApprovedPRManager, self).get_queryset().filter(status='approved')


class SubmittedPRManager(models.Manager):
    def get_queryset(self):
        return super(SubmittedPRManager, self).get_queryset().filter(status='submitted')


class RejectedPRManager(models.Manager):
    def get_queryset(self):
        return super(RejectedPRManager, self).get_queryset().filter(status='rejected')


# For Purchase Orders
class DraftPOManager(models.Manager):
    def get_queryset(self):
        return super(DraftPOManager, self).get_queryset().filter(status='draft')


class AwaitingPOManager(models.Manager):
    def get_queryset(self):
        return super(AwaitingPOManager, self).get_queryset().filter(status='awaiting')


class CompletedPOManager(models.Manager):
    def get_queryset(self):
        return super(CompletedPOManager, self).get_queryset().filter(status='completed')


class CancelledPOManager(models.Manager):
    def get_queryset(self):
        return super(CancelledPOManager, self).get_queryset().filter(status='cancelled')


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super(ActiveManager, self).get_queryset().filter(is_hidden=False)


class HiddenManager(models.Manager):
    def get_queryset(self):
        return super(HiddenManager, self).get_queryset().filter(is_hidden=True)


# To generate unique id for purchase requests
def generate_unique_pr_id():
    last_request = PurchaseRequest.objects.order_by('id').last()
    if last_request:
        last_id = int(last_request.id[2:])
        new_id = f"PR{last_id + 1:06d}"
    else:
        new_id = "PR000001"
    return new_id


# To generate unique id for request for quotations
def generate_unique_rfq_id():
    last_request = RequestForQuotation.objects.order_by('id').last()
    if last_request:
        last_id = int(last_request.id[2:])
        new_id = f"RFQ{last_id + 1:06d}"
    else:
        new_id = "RFQ000001"
    return new_id


# To generate unique id for purchase orders
def generate_unique_po_id():
    last_request = PurchaseOrder.objects.order_by('id').last()
    if last_request:
        last_id = int(last_request.id[2:])
        new_id = f"PO{last_id + 1:06d}"
    else:
        new_id = "PO000001"
    return new_id


class UnitOfMeasure(models.Model):
    name = models.CharField(max_length=100)
    description = CKEditor5Field(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-created_on']
        verbose_name_plural = 'Units of Measure'

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    name = models.CharField(max_length=100)
    description = CKEditor5Field(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-updated_on']
        verbose_name_plural = 'Product Categories'

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    unit_of_measure = models.ForeignKey(UnitOfMeasure, on_delete=models.SET_NULL, null=True)
    type = models.CharField(max_length=64, choices=PRODUCT_TYPE, default="goods")
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, related_name='products')
    company = models.ForeignKey('Vendor', on_delete=models.CASCADE)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-created_on']

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=100)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-id']

    def __str__(self):
        return self.name


class VendorCategory(models.Model):
    name = models.CharField(max_length=100)
    description = CKEditor5Field(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-updated_on']
        verbose_name_plural = 'Vendor Categories'

    def __str__(self):
        return self.name


class Vendor(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    company_name = models.CharField(max_length=200)
    category = models.ForeignKey(VendorCategory, on_delete=models.SET_NULL, null=True, related_name="vendors")
    email = models.EmailField(max_length=100)
    address = models.CharField(max_length=300, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-updated_on']

    def __str__(self):
        return self.company_name

    # Email functionality:
    def send_email(self, subject, message, **kwargs):
        """
        Sends an email to a vendor.
        """
        email = EmailMessage(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            to=[self.email]
        )
        email.content_subtype = "html"  # This is necessary to ensure the email is sent as HTML
        email.send()

    @classmethod
    def send_mass_email(cls, subject, message, **kwargs):
        """
        Sends an email to multiple Vendors.
        """
        vendors = cls.objects.all()
        vendor_emails = [vendor.email for vendor in vendors]
        email = EmailMessage(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            bcc=vendor_emails,
        )
        email.content_subtype = "html"  # This is necessary to ensure the email is sent as HTML
        email.send()


class PurchaseRequest(models.Model):
    id = models.CharField(max_length=10, primary_key=True, unique=True, default=generate_unique_pr_id, editable=False)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchase_requests')
    # requester = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=PURCHASE_REQUEST_STATUS, default='draft')
    purpose = CKEditor5Field(blank=True, null=True)
    suggested_vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()
    pr_draft = DraftPRManager()
    pr_approved = ApprovedPRManager()
    pr_submitted = SubmittedPRManager()
    pr_rejected = RejectedPRManager()

    @property
    def total_price(self):
        total_price = sum(item.total_price for item in self.items.all())
        return total_price

    class Meta:
        ordering = ['is_hidden', '-date_updated']

    def __str__(self):
        return self.id


class PurchaseRequestItem(models.Model):
    purchase_request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name='items')
    date_created = models.DateTimeField(auto_now_add=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    description = CKEditor5Field(null=True, blank=True)
    qty = models.PositiveIntegerField()
    estimated_unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    objects = models.Manager()

    class Meta:
        ordering = ['-date_created']

    def __str__(self):
        return self.product.name


# this is a signal that calculates the qty times the unit price automatically
@receiver(pre_save, sender=PurchaseRequestItem)
def update_total_price(sender, instance, **kwargs):
    instance.total_price = instance.qty * instance.estimated_unit_price


class RequestForQuotation(models.Model):
    id = models.CharField(max_length=10, primary_key=True, unique=True, default=generate_unique_rfq_id, editable=False)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    expiry_date = models.DateTimeField(null=True, blank=True,
                                       help_text="Leave blank for no expiry")
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE)
    status = models.CharField(max_length=100, choices=RFQ_STATUS, default='awaiting')
    is_hidden = models.BooleanField(default=False)

    # def __init__(self, *args, **kwargs):
    #     self._formatted_id = None
    #     super(RequestForQuotation, self).__init__(*args, **kwargs)
    #
    # def get_formatted_id(self, *args, **kwargs):
    #     if self._formatted_id is None:
    #         self.set_formatted_id()
    #     return self._formatted_id
    #
    # def set_formatted_id(self, *args, **kwargs):
    #     self._formatted_id = "RFQ" + "{:05d}".format(self.id)
    #
    # formatted_id = property(get_formatted_id, set_formatted_id, doc="formatted_id property")

    objects = models.Manager()
    vendor_selected_rfqs = SelectedVendorManager()
    vendor_awaiting_rfqs = AwaitingVendorManager()
    vendor_cancelled_rfqs = CancelledVendorManager()

    class Meta:
        ordering = ['is_hidden', '-date_updated']

    def __str__(self):
        return self.id

    @property
    def rfq_total_price(self):
        rfq_total_price = sum(item.total_price for item in self.items.all())
        return rfq_total_price

    # @property
    # def duration_till_expiration(self):
    #     if self.expiry_date:
    #         return datetime(self.expiry_date) - datetime(self.date_opened)
    #     return None

    # @property
    # def is_expired(self) -> bool:
    #     """ to check whether duration already expired or yet """
    #     if self.expiry_date:
    #         return datetime.now() > self.expiry_date
    #     return False

    # @property
    # def next_expiry_date(self):
    #     """ to get next expiry date """
    #     if self.expiry_date:
    #         return datetime(self.expiry_date) + timedelta(days=1)
    #     return None

    def send_email(self):
        """
        A function to send an email containing the RFQ to the vendor when a RFQ is created.
        """
        subject = f"Request for Quotation: {self.id}"
        rfq_data = {
            'id': self.id,
            'date_created': self.date_created.strftime('%Y-%m-%d'),
            'date_updated': self.date_updated.strftime('%Y-%m-%d'),
            'expiry_date': self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else None,
            'vendor': self.vendor.company_name,
            'status': self.status,
            'items': [
                {
                    'product': item.product.name,
                    'description': item.description,
                    'qty': item.qty,
                    'estimated_unit_price': str(item.estimated_unit_price),
                    'total_price': str(item.total_price)
                }
                for item in self.items.all()
            ],
            'rfq_total_price': str(self.rfq_total_price)
        }
        message = json.dumps(rfq_data)
        self.vendor.send_mass_email(subject, message)


class RequestForQuotationItem(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    request_for_quotation = models.ForeignKey(RequestForQuotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    description = CKEditor5Field(null=True, blank=True)
    qty = models.PositiveIntegerField(default=1, verbose_name="QTY")
    estimated_unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    objects = models.Manager()

    def __init__(self, *args, **kwargs):
        self._total_price = None
        super(RequestForQuotationItem, self).__init__(*args, **kwargs)

    def get_total_price(self, *args, **kwargs):
        if self._total_price is None:
            self.set_total_price()
        return self._total_price

    def set_total_price(self, *args, **kwargs):
        self._total_price = self.estimated_unit_price * self.qty

    total_price = property(get_total_price, set_total_price, doc="total price property")

    def __str__(self):
        return self.product.name

    class Meta:
        ordering = ['-date_created']


class RFQVendorQuote(models.Model):
    date_opened = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    rfq = models.ForeignKey("RequestForQuotation", on_delete=models.CASCADE, related_name='quotes')
    vendor = models.ForeignKey("Vendor", on_delete=models.CASCADE, related_name='rfq_quotes')
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    @property
    def quote_total_price(self):
        quote_total_price = sum(item.total_price for item in self.items.all())
        return quote_total_price

    class Meta:
        ordering = ['is_hidden', '-date_updated']

    def __str__(self):
        return f"{self.vendor} - {self.rfq}"


class RFQVendorQuoteItem(models.Model):
    rfq_vendor_quote = models.ForeignKey("RFQVendorQuote", on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    description = CKEditor5Field(null=True, blank=True)
    qty = models.PositiveIntegerField(default=1, verbose_name="QTY")
    estimated_unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    objects = models.Manager()

    def __init__(self, *args, **kwargs):
        self._total_price = None
        super(RFQVendorQuoteItem, self).__init__(*args, **kwargs)

    def get_total_price(self, *args, **kwargs):
        if self._total_price is None:
            self.set_total_price()
        return self._total_price

    def set_total_price(self, *args, **kwargs):
        self._total_price = self.estimated_unit_price * self.qty

    total_price = property(get_total_price, set_total_price, doc="total price property")

    def __str__(self):
        return self.product.name


class PurchaseOrder(models.Model):
    id = models.CharField(max_length=10, primary_key=True, unique=True, default=generate_unique_po_id, editable=False)
    status = models.CharField(max_length=200, choices=PURCHASE_ORDER_STATUS, default="draft")
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    vendor = models.ForeignKey("Vendor", on_delete=models.CASCADE, related_name="orders")
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()
    po_draft = DraftPOManager()
    po_awaiting = AwaitingPOManager()
    po_completed = CompletedPOManager()
    po_cancelled = CancelledPOManager()

    class Meta:
        ordering = ['is_hidden', '-date_updated']

    def __str__(self):
        return self.id

    @property
    def po_total_price(self):
        po_total_price = sum(item.total_price for item in self.items.all())
        return po_total_price

    def send_email(self):
        """
        A function to send an email containing the Purchase Order to the vendor when a Purchase Order is created.
        """
        subject = f"Purchase Order: {self.id}"
        po_data = {
            'id': self.id,
            'date_created': self.date_created.strftime('%Y-%m-%d'),
            'date_updated': self.date_updated.strftime('%Y-%m-%d'),
            'status': self.status,
            'vendor': self.vendor.company_name,
            'items': [
                {
                    'product': item.product.name,
                    'description': item.description,
                    'qty': item.qty,
                    'estimated_unit_price': str(item.estimated_unit_price),
                    'total_price': str(item.total_price)
                }
                for item in self.items.all()
            ],
            'po_total_price': str(self.po_total_price)
        }
        message = json.dumps(po_data)
        self.vendor.send_mass_email(subject, message)


class PurchaseOrderItem(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    purchase_order = models.ForeignKey("PurchaseOrder", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    description = CKEditor5Field(null=True, blank=True)
    qty = models.PositiveIntegerField(default=1, verbose_name="QTY")
    estimated_unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    objects = models.Manager()

    class Meta:
        ordering = ['-date_created']

    def __init__(self, *args, **kwargs):
        self._total_price = None
        super(PurchaseOrderItem, self).__init__(*args, **kwargs)

    def get_total_price(self, *args, **kwargs):
        if self._total_price is None:
            self.set_total_price()
        return self._total_price

    def set_total_price(self, *args, **kwargs):
        self._total_price = self.estimated_unit_price * self.qty

    total_price = property(get_total_price, set_total_price, doc="total price property")

    def __str__(self):
        return self.product.name


class POVendorQuote(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    purchase_order = models.ForeignKey("PurchaseOrder", on_delete=models.CASCADE, related_name='quotes')
    vendor = models.ForeignKey("Vendor", on_delete=models.CASCADE, related_name='po_quotes')
    is_hidden = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        ordering = ['is_hidden', '-date_updated']

    def __str__(self):
        return f"{self.vendor} - {self.purchase_order}"

    @property
    def quote_total_price(self):
        quote_total_price = sum(item.total_price for item in self.items.all())
        return quote_total_price


class POVendorQuoteItem(models.Model):
    po_vendor_quote = models.ForeignKey("POVendorQuote", on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    description = CKEditor5Field(null=True, blank=True)
    qty = models.PositiveIntegerField(default=1, verbose_name="QTY")
    estimated_unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    objects = models.Manager()

    def __init__(self, *args, **kwargs):
        self._total_price = None
        super(POVendorQuoteItem, self).__init__(*args, **kwargs)

    def get_total_price(self, *args, **kwargs):
        if self._total_price is None:
            self.set_total_price()
        return self._total_price

    def set_total_price(self, *args, **kwargs):
        self._total_price = self.estimated_unit_price * self.qty

    total_price = property(get_total_price, set_total_price, doc="total price property")

    def __str__(self):
        return self.product.name
