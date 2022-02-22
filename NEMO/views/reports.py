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
    if start_date != '0' or end_date != '0':
        tool_data = UsageEvent.objects.filter(end__gt=start_date, end__lte=end_date)
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
        return render(request, "reports/usage_events.html", {'context': new_d, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/usage_events.html", {'start': start_date, 'end': end_date})


def active_users(request):
    start_date, end_date = date_parameters_dictionary(request)
    if start_date != '0' or end_date != '0':
        tool_data = UsageEvent.objects.filter(end__gt=start_date, end__lte=end_date)
        d = {}
        for tool in tool_data:
            d[tool.user] = tool.user
        keys_values = d.items()
        new_d = {str(key): str(value) for key, value in keys_values}
        total_d = {'Total': str(len(new_d))}
        res = {**total_d, **new_d}
        print(res)
        return render(request, "reports/active_users.html", {'context': res, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/active_users.html", {'start': start_date, 'end': end_date})


def cumulative_users(request):
    start_date, end_date = date_parameters_dictionary(request)
    if start_date != '0' or end_date != '0':
        # user_data = User.objects.all()
        user_data = User.objects.filter(date_joined__gt=start_date, date_joined__lte=end_date)
        d = {}
        for user in user_data:
            d['first_name'] = user.first_name
            d['last_name'] = user.last_name
            d['type'] = user.type
            d['date_joined'] = str(user.date_joined)[0:10]
        keys_values = d.items()
        new_d = {str(key): str(value) for key, value in keys_values}
        print(new_d)
        return render(request, "reports/cumulative_users.html", {'context': new_d, 'start': start_date, 'end': end_date})
    else:
        return render(request, "reports/active_users.html", {'start': start_date, 'end': end_date})
