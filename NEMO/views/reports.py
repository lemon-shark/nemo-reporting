import collections

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.shortcuts import render
from dateutil import parser
from NEMO.models import UsageEvent, User


def reports(request):
    return render(request, 'reports/reports.html')


def convert_timedelta(duration):
    days, seconds = duration.days, duration.seconds
    hours = days * 24 + seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = (seconds % 60)
    return '{} hour{}, {} minute{}, {} second{}'.format(hours, 's' if hours != 1 else '',
                                                        minutes, 's' if minutes != 1 else '',
                                                        seconds, 's' if seconds != 1 else '')


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
        tool_data = UsageEvent.objects.only("tool", "start", "end").select_related('tool').filter(end__gt=start_date, end__lte=end_date)
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
        tool_data = UsageEvent.objects.only("user", "end").select_related('user').filter(end__gt=start_date, end__lte=end_date)
        d = {}
        for tool in tool_data:
            d[tool.user] = tool.user
        keys_values = d.items()
        new_d = {str(key): str(value) for key, value in keys_values}
        if len(new_d) != 0:
            # total_d = {'Total': str(len(new_d))}
            # res = {**total_d, **new_d}
            # print(res)
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
        # print(start_date)
        # print(end_date)
        # print(User.objects.all())
        user_data = User.objects.filter(date_joined__gte=start_date, date_joined__lte=end_date)
        print(user_data)
        d = collections.defaultdict(list)
        for user in user_data:
            d['first_name'].append(user.first_name)
            list_of_data[0].append(user.first_name)
            d['last_name'].append(user.last_name)
            list_of_data[1].append(user.last_name)
            d['type'].append(user.type)
            list_of_data[2].append(user.type)
            print(user.date_joined)
            d['date_joined'].append(str(user.date_joined)[0:10])
            list_of_data[3].append(str(user.date_joined)[0:10])
        keys_values = d.items()
        new_d = {str(key): str(value) for key, value in keys_values}
        print(new_d)
        return render(request, "reports/cumulative_users.html", {'context': new_d, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/cumulative_users.html", {'start': start_date, 'end': end_date})
