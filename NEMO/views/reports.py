import collections
import itertools
from typing import io
import pandas as pd

from NEMO_billing.invoices.models import ProjectBillingDetails
from allauth.socialaccount.providers.mediawiki.provider import settings
from django.forms import DecimalField
from dateutil import parser
from NEMO.models import UsageEvent, User

import io
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import List

from NEMO.decorators import synchronized
from NEMO.models import Account, Project
from NEMO.utilities import month_list
from NEMO.views.pagination import SortedPaginator
from django.conf import settings
from django.contrib import messages
from django.db.models import Case, DecimalField, F, Sum, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.safestring import mark_safe

from NEMO_billing.invoices.exceptions import (
    InvoiceAlreadyExistException,
    InvoiceItemsNotInFacilityException,
    NoProjectCategorySetException,
    NoProjectDetailsSetException,
    NoRateSetException,
)
from NEMO_billing.invoices.invoice_generator import generate_monthly_invoice
from NEMO_billing.invoices.models import Invoice, InvoiceConfiguration, InvoicePayment, InvoiceSummaryItem
from NEMO_billing.models import CoreFacility


def reports(request):
    return render(request, 'reports/reports.html')


def convert_timedelta(duration):
    days, seconds = duration.days, duration.seconds
    hours = days * 24 + seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = (seconds % 60)
    return '{}:{}:{}'.format(hours, minutes, seconds)


def parse_start_end_date(start, end):
    start = timezone.make_aware(parser.parse(start), timezone.get_current_timezone())
    end = timezone.make_aware(parser.parse(end), timezone.get_current_timezone())
    return start, end


def date_parameters_dictionary(request):
    data = dict(request.POST)
    if data.get('start_time') and data.get('end_time'):
        start_date, end_date = parse_start_end_date(data.get('start_time')[0], data.get('end_time')[0])
    else:
        start_date, end_date = '0', '0'
    return start_date, end_date


def usage_events(request):
    start_date, end_date = date_parameters_dictionary(request)
    # page = request.GET.get('page', 1)
    if start_date != '0' or end_date != '0':
        tool_data = UsageEvent.objects.only("tool", "start", "end").select_related('tool').filter(end__gt=start_date,
                                                                                                  end__lte=end_date).order_by(
            'tool')
        d = {}
        print(start_date)
        print(end_date)
        for tool in tool_data:
            start = tool.start
            if tool.end:
                end = tool.end
                if tool.tool not in d:
                    d[tool.tool] = end - start
                else:
                    d[tool.tool] += end - start
        keys_values = d.items()
        new_d = {str(key): str(convert_timedelta(value)) for key, value in keys_values}
        print(new_d)
        # paginator = Paginator(tuple(new_d.items()), 25)
        # try:
        #     tools = paginator.page(page)
        #     print(page)
        # except PageNotAnInteger:
        #     tools = paginator.page(1)
        # except EmptyPage:
        #     # if we exceed the page limit we return the last page
        #     tools = paginator.page(paginator.num_pages)
        #     print(paginator.num_pages)
        return render(request, "reports/usage_events.html", {'context': new_d, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/usage_events.html", {'start': start_date, 'end': end_date})


def active_users(request):
    start_date, end_date = date_parameters_dictionary(request)
    if start_date != '0' or end_date != '0':
        tool_data = UsageEvent.objects.only("user", "end").select_related('user').filter(end__gt=start_date,
                                                                                         end__lte=end_date).order_by(
            "user")
        d = {}
        for tool in tool_data:
            d[tool.user] = tool.user
        keys_values = d.items()
        new_d = {str(key): str(value) for key, value in keys_values}
        if len(new_d) != 0:
            total = len(new_d)
            return render(request, "reports/active_users.html", {'context': new_d, 'total': total, 'start': start_date,
                                                                 'end': end_date})
        else:
            return render(request, "reports/active_users.html", {'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/active_users.html", {'start': start_date, 'end': end_date})


def cumulative_users(request):
    start_date, end_date = date_parameters_dictionary(request)
    list_of_data = [[] for i in range(4)]
    if start_date != '0' or end_date != '0':
        user_data = User.objects.only("first_name", "last_name", "type", "date_joined").filter(
            date_joined__gte=start_date, date_joined__lte=end_date).order_by("date_joined")
        print(user_data)
        for user in user_data:
            list_of_data[0].append(user.first_name)
            list_of_data[1].append(user.last_name)
            list_of_data[2].append(user.type)
            print(user.date_joined)
            list_of_data[3].append(str(user.date_joined)[0:10])
        print(list_of_data)
        list_output = list(map(list, itertools.zip_longest(*list_of_data, fillvalue=None)))
        print(list_output)
        return render(request, "reports/cumulative_users.html",
                      {'context': list_output, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/cumulative_users.html", {'start': start_date, 'end': end_date})


def groups(request):
    start_date, end_date = date_parameters_dictionary(request)
    list_of_data = [[] for i in range(3)]
    if start_date != '0' or end_date != '0':
        groups_data = Account.objects.filter(start_date__gte=start_date, start_date__lte=end_date).order_by(
            'start_date')
        # print(groups_data)
        for group in groups_data:
            list_of_data[0].append(group.name)
            list_of_data[1].append(group.type)
            list_of_data[2].append(str(group.start_date))
            # print(group.start_date)
        # print(list_of_data)
        print(list_of_data[1])
        breakdown = collections.Counter(list_of_data[1]).most_common()
        print(type(breakdown))
        print(breakdown)
        list_output = list(map(list, itertools.zip_longest(*list_of_data, fillvalue=None)))
        # print(list_output)
        return render(request, "reports/groups.html", {'context': list_output, 'breakdown': breakdown,
                                                       'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/groups.html", {'start': start_date, 'end': end_date})


def facility_usage(request):
    start_date, end_date = date_parameters_dictionary(request)
    if start_date != '0' or end_date != '0':
        facility_data = UsageEvent.objects.only("project", "start", "end").select_related('project').filter(
            end__gt=start_date, end__lte=end_date)
        project_list = UsageEvent.objects.only("project", "start", "end").select_related('project'). \
            filter(end__gt=start_date, end__lte=end_date).values_list('project')
        project_data = ProjectBillingDetails.objects.only("project", "category").select_related('category').filter(
            project__in=project_list)
        d = {}
        d_category = {}
        category = []
        # print(project_list)
        for project in project_data:
            d_category[project] = project.category
            category.append(project.category)
        category_output = collections.Counter(category).most_common()
        total = sum(j for i, j in category_output)
        # print(d_category)

        for facility in facility_data:
            start = facility.start
            if facility.end:
                end = facility.end
                if facility.project not in d:
                    d[facility.project] = end - start
                else:
                    d[facility.project] += end - start
        keys_values = d.items()
        new_d = {str(key): str(convert_timedelta(value)) for key, value in keys_values}
        datetime_d = {str(key): value for key, value in keys_values}
        # print(new_d)
        df1 = pd.DataFrame(new_d.items(), columns=['project', 'time'])
        df1['project'] = df1['project'].astype(str)
        df2 = pd.DataFrame(d_category.items(), columns=['project', 'category'])
        df2['project'] = df2['project'].astype(str)
        df3 = pd.DataFrame(datetime_d.items(), columns=['project', 'time'])
        df3['project'] = df3['project'].astype(str)
        left_join = pd.merge(df1, df2, on='project', how='left')
        datetime_left_join = pd.merge(df3, df2, on='project', how='left')
        print(datetime_left_join)
        by_category = datetime_left_join.drop('project', 1)
        # category_list = by_category.values.tolist()
        # print(category_list)
        by_category = by_category.astype({"category": str})
        # print(by_category)
        group_category = by_category.groupby('category')['time'].sum()
        category_output = group_category.reset_index()
        category_output['time'] = category_output['time'].apply(lambda x: str(convert_timedelta(x)))
        print(category_output)

        # print(category_output)
        all_join = left_join.to_dict('records')
        category_dict = category_output.to_dict('records')
        # print(type(all_join))
        # keys_values = category_dict.items()
        # category_output = {str(key): str(convert_timedelta(value)) for key, value in keys_values}

        return render(request, "reports/facility_usage.html", {'context': all_join, 'category': category_dict,
                                                                'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/facility_usage.html", {'start': start_date, 'end': end_date})


def invoices(request):
    start_date, end_date = date_parameters_dictionary(request)
    list_of_data = [[] for i in range(3)]
    if start_date != '0' or end_date != '0':
        invoice_data = Invoice.objects.only("id", "created_date", "project_details").filter(
            created_date__gt=start_date, created_date__lte=end_date).order_by("created_date")
        invoice_list = Invoice.objects.only("total_amount", "created_date").filter(
            created_date__gt=start_date, created_date__lte=end_date).values_list('id')
        invoicesummary_data = InvoiceSummaryItem.objects.only("invoice", "amount", "core_facility", "name").filter(
            invoice_id__in=invoice_list).filter(name="Subtotal")

        for each in invoice_data:
            list_of_data[0].append(str(each.created_date.strftime("%b")) + "-" + str(each.created_date.year))
            list_of_data[1].append(int(each.id))
            list_of_data[2].append(str(each.project_details.category))
        # print(list_of_data)
        list_transpose = list(map(list, itertools.zip_longest(*list_of_data, fillvalue=None)))
        # print(list_transpose)
        df1 = pd.DataFrame(list_transpose, columns=['Period', 'Invoice', 'Project'])
        # print(df1)

        list_of_summarydata = [[] for i in range(3)]
        for invoicesummary in invoicesummary_data:
            list_of_summarydata[0].append(invoicesummary.core_facility)
            list_of_summarydata[1].append(int(invoicesummary.invoice_id))
            list_of_summarydata[2].append(invoicesummary.amount)
        list_summary_transpose = list(map(list, itertools.zip_longest(*list_of_summarydata, fillvalue=None)))
        df2 = pd.DataFrame(list_summary_transpose, columns=['Facility', 'Invoice', 'Amount'])
        # print(df2)
        left_join = pd.merge(df1, df2, on='Invoice', how='left')
        # print(left_join)
        left_join = left_join.drop('Invoice', 1)
        row_sum = left_join.groupby(['Period', 'Project', 'Facility']).agg('sum')
        result = row_sum.reset_index()
        result['Amount'] = result['Amount'].apply(lambda x: "${:,.2f}".format(x))
        # print(result)
        joined = result.to_dict('records')
        # print(joined)
        return render(request, "reports/invoices.html",
                      {'context': joined, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/invoices.html", {'start': start_date, 'end': end_date})


def aging_schedule(request):
        # Add outstanding balance and total tax that will be sortable columns
        invoice_list = (
            Invoice.objects.filter(voided_date=None)
                .annotate(outstanding=F("total_amount") - Coalesce(Sum("invoicepayment__amount"), 0))
                .annotate(
                total_tax=Sum(
                    Case(
                        When(
                            invoicesummaryitem__summary_item_type=InvoiceSummaryItem.InvoiceSummaryItemType.TAX,
                            then=F("invoicesummaryitem__amount"),
                        ),
                        output_field=DecimalField(),
                        default=0,
                    )
                )
            )
        )

        page = SortedPaginator(invoice_list, request, order_by="-created_date").get_current_page()

        core_facilities = CoreFacility.objects.all()

        return render(
            request,
            "reports/aging_schedule.html",
            {
                "page": page,
                "month_list": month_list(since=settings.INVOICE_MONTH_LIST_SINCE),
                "projects": Project.objects.all().order_by("account__name"),
                "configuration_list": InvoiceConfiguration.objects.all(),
                "invoices_search": Invoice.objects.all(),
                "core_facilities": core_facilities,
                "display_general_facility": not core_facilities.exists()
                                            or not settings.INVOICE_ALL_ITEMS_MUST_BE_IN_FACILITY,
            },
        )


@synchronized()
def generate_monthly_invoices(request):
        try:
            project_id: str = request.POST["project_id"]
            configuration_id = request.POST["configuration_id"]
            configuration = get_object_or_404(InvoiceConfiguration, id=configuration_id)
            if project_id == "All":
                for project in Project.objects.all():
                    generate_monthly_invoice(request.POST["month"], project, configuration, request.user)
            elif project_id.startswith("account:"):
                account: Account = get_object_or_404(Account, id=project_id.replace("account:", ""))
                for project in account.project_set.all():
                    generate_monthly_invoice(request.POST["month"], project, configuration, request.user)
            else:
                project = get_object_or_404(Project, id=project_id)
                invoice = generate_monthly_invoice(request.POST["month"], project, configuration, request.user, True)
                if not invoice:
                    messages.warning(request, f"No billable items were found for project: {project}")
        except NoProjectDetailsSetException as e:
            link = reverse("project", args=[e.project.id])
            message = "Invoice generation failed: " + e.msg + f" - click <a href='{link}'>here</a> to add some."
            messages.error(request, mark_safe(message))
        except NoRateSetException as e:
            link = reverse("rates")
            message = "Invoice generation failed: " + e.msg + f" - click <a href='{link}'>here</a> to create one."
            messages.error(request, mark_safe(message))
        except InvoiceAlreadyExistException as e:
            link = reverse("view_invoice", args=[e.invoice.id])
            message = "Invoice generation failed: " + e.msg + f" - click <a href='{link}'>here</a> to view it."
            messages.error(request, mark_safe(message))
        except NoProjectCategorySetException as e:
            link = reverse("project", args=[e.project.id])
            message = "Invoice generation failed: " + e.msg + f" - click <a href='{link}'>here</a> to set it."
            messages.error(request, mark_safe(message))
        except InvoiceItemsNotInFacilityException as e:
            messages.error(request, e.msg)
        return redirect("invoices")


def view_invoice(request, invoice_id):
        invoice = get_object_or_404(Invoice, id=invoice_id)
        return render(
            request, "invoices/invoice.html", {"invoice": invoice, "core_facilities": CoreFacility.objects.exists()}
        )


def review_invoice(request, invoice_id):
        invoice = get_object_or_404(Invoice, id=invoice_id)
        if not invoice.reviewed_date:
            invoice.reviewed_date = timezone.now()
            invoice.reviewed_by = request.user
            invoice.save()
            messages.success(request, f"Invoice {invoice.invoice_number} was successfully marked as reviewed.")
        else:
            messages.error(request, f"Invoice {invoice.invoice_number} has already been reviewed.")
        return redirect("view_invoice", invoice_id=invoice_id)


def send_invoice(request, invoice_id):
        invoice = get_object_or_404(Invoice, id=invoice_id)
        if invoice.reviewed_date:
            if not invoice.project_details.email_to():
                link = reverse("project", args=[invoice.project_details.project.id])
                messages.error(
                    request,
                    mark_safe(
                        f"Invoice {invoice.invoice_number} could not sent because no email is set on the project - click <a href='{link}'>here</a> to add some"
                    ),
                )
            else:
                sent = invoice.send()
                if sent:
                    messages.success(request, f"Invoice {invoice.invoice_number} was successfully sent.")
                else:
                    messages.error(request, f"Invoice {invoice.invoice_number} could not be sent.")
        else:
            messages.error(request, f"Invoice {invoice.invoice_number} needs to be reviewed before sending.")
        return redirect("view_invoice", invoice_id=invoice_id)


def void_invoice(request, invoice_id):
        invoice = get_object_or_404(Invoice, id=invoice_id)
        if not invoice.voided_date:
            invoice.voided_date = timezone.now()
            invoice.voided_by = request.user
            invoice.save()
            messages.success(request, f"Invoice {invoice.invoice_number} was successfully marked as void.")
        else:
            messages.error(request, f"Invoice {invoice.invoice_number} is already void.")
        return redirect("view_invoice", invoice_id=invoice_id)


def zip_invoices(request):
        invoice_ids: List[str] = request.POST.getlist("selected_invoice_id[]")
        if not invoice_ids:
            return redirect("invoices")
        else:
            return zip_response(request, Invoice.objects.filter(id__in=invoice_ids))


def invoice_payment_received(request, invoice_id):
        invoice = get_object_or_404(Invoice, id=invoice_id)
        payment = InvoicePayment()
        payment.invoice = invoice
        payment.created_by = request.user
        payment.updated_by = request.user
        payment.payment_received = datetime.strptime(request.POST["payment_received_date"], "%m/%d/%Y")
        payment.amount = Decimal(request.POST["payment_received_amount"])
        payment.note = request.POST.get("payment_note")
        payment.save()
        messages.success(
            request,
            f"The payment of {payment.amount_display()} for invoice {invoice.invoice_number} was marked as received on {date_format(payment.payment_received)}.",
        )
        return redirect("view_invoice", invoice_id=invoice_id)


def invoice_payment_processed(request, payment_id):
        payment = get_object_or_404(InvoicePayment, id=payment_id)
        payment.updated_by = request.user
        payment.payment_processed = datetime.strptime(request.POST["payment_processed_date"], "%m/%d/%Y")
        payment.save()
        messages.success(
            request,
            f"The payment of {payment.amount_display()} for invoice {payment.invoice.invoice_number} was marked as processed on {date_format(payment.payment_processed)}.",
        )
        return redirect("view_invoice", invoice_id=payment.invoice_id)


def send_invoice_payment_reminder(request):
        return do_send_invoice_payment_reminder()

def do_send_invoice_payment_reminder():
        today = timezone.now()
        unpaid_invoices = Invoice.objects.filter(due_date__lte=today, voided_date=None)
        for unpaid_invoice in unpaid_invoices:
            if unpaid_invoice.total_outstanding_amount() > Decimal(0):
                if not unpaid_invoice.last_reminder_sent_date:
                    unpaid_invoice.send_reminder()
                else:
                    # Check days since last reminder sent
                    time_diff = today - unpaid_invoice.last_reminder_sent_date
                    too_long_since_last = (
                            unpaid_invoice.configuration.reminder_frequency
                            and time_diff.days >= unpaid_invoice.configuration.reminder_frequency
                    )
                    # Send reminder if none has been sent yet, or if it's been too long
                    if too_long_since_last:
                        unpaid_invoice.send_reminder()
        return HttpResponse()

def zip_response(request, invoice_list: List[Invoice]):
        generated_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        parent_folder_name = f"invoices_{generated_date}"
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, mode="w", compression=zipfile.ZIP_DEFLATED) as backup_zip:
            for invoice in invoice_list:
                if invoice.file:
                    backup_zip.write(invoice.file.path, f"{parent_folder_name}/" + invoice.filename_for_zip())
        response = HttpResponse(zip_io.getvalue(), content_type="application/x-zip-compressed")
        response["Content-Disposition"] = "attachment; filename=%s" % parent_folder_name + ".zip"
        response["Content-Length"] = zip_io.tell()
        return response
