import collections
import itertools
from typing import io
import pandas as pd
from datetime import date

from NEMO_billing.invoices.models import ProjectBillingDetails
from allauth.socialaccount.providers.mediawiki.provider import settings
from django.forms import DecimalField
from dateutil import parser
from NEMO.models import UsageEvent, User, AreaAccessRecord

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


def area_events(request):
    start_date, end_date = date_parameters_dictionary(request)
    # page = request.GET.get('page', 1)
    if start_date != '0' or end_date != '0':
        area_data = AreaAccessRecord.objects.only("area", "start", "end").select_related('area').filter(end__gt=start_date,
                                                                                                  end__lte=end_date)
        d = {}
        print(start_date)
        print(end_date)
        for area in area_data:
            start = area.start
            if area.end:
                end = area.end
                if area.area not in d:
                    d[area.area] = end - start
                else:
                    d[area.area] += end - start
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
        return render(request, "reports/area_events.html", {'context': new_d, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/area_events.html", {'start': start_date, 'end': end_date})



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
            list_of_data[3].append(str(user.date_joined)[0:10])
        list_output = list(map(list, itertools.zip_longest(*list_of_data, fillvalue=None)))
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
        project_data = ProjectBillingDetails.objects.only("project", "category", "no_charge").select_related('category').filter(
            project__in=project_list)
            # .exclude(no_tax=True)
        d = {}
        d_category = {}
        category = []
        print(project_data)
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
        )

        start_date, end_date = date_parameters_dictionary(request)
        list_of_data = [[] for i in range(5)]
        if start_date != '0' or end_date != '0':
            invoice_data = Invoice.objects.only("invoice_number", "created_date", "reviewed_date", "total_amount", "due_date").filter(
                created_date__gt=start_date, created_date__lte=end_date)
            d = {}
            print(start_date)
            print(end_date)
            for each in invoice_data:
                list_of_data[0].append(each.invoice_number)
                list_of_data[1].append(str(each.created_date)[0:19])
                list_of_data[2].append(str(each.reviewed_date)[0:19])
                list_of_data[3].append("${:,.2f}".format(each.total_amount))
                list_of_data[4].append((datetime.utcnow().date() - each.due_date).days)

            list_output = list(map(list, itertools.zip_longest(*list_of_data, fillvalue=None)))
            print(list_output)

            return render(request, "reports/aging_schedule.html",
                          {'context': list_output, 'start': start_date, 'end': end_date})
        else:
            return render(request, "reports/aging_schedule.html", {'start': start_date, 'end': end_date})


# def area_events(request):
#     start_date, end_date = date_parameters_dictionary(request)
#     # page = request.GET.get('page', 1)
#     if start_date != '0' or end_date != '0':
#         tool_data = .objects.only("tool", "start", "end").select_related('tool').filter(end__gt=start_date,
#                                                                                                   end__lte=end_date).order_by(
#             'tool')
#         d = {}
#         print(start_date)
#         print(end_date)
#         for tool in tool_data:
#             start = tool.start
#             if tool.end:
#                 end = tool.end
#                 if tool.tool not in d:
#                     d[tool.tool] = end - start
#                 else:
#                     d[tool.tool] += end - start
#         keys_values = d.items()
#         new_d = {str(key): str(convert_timedelta(value)) for key, value in keys_values}
#         print(new_d)
#         # paginator = Paginator(tuple(new_d.items()), 25)
#         # try:
#         #     tools = paginator.page(page)
#         #     print(page)
#         # except PageNotAnInteger:
#         #     tools = paginator.page(1)
#         # except EmptyPage:
#         #     # if we exceed the page limit we return the last page
#         #     tools = paginator.page(paginator.num_pages)
#         #     print(paginator.num_pages)
#         return render(request, "reports/usage_events.html", {'context': new_d, 'start': start_date, 'end': end_date})
#     else:
#         return render(request, "reports/usage_events.html", {'start': start_date, 'end': end_date})
#


