# Из последнего над чем я работал было несколько свежих проектов и 1 на python 2.7

"""
Это код из старого проекта
"""
# coding=utf-8
import logging

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from imagekit.exceptions import MissingSource

from catalog.models import Item
from catalog.utils import is_digit
from core.models import Account


if settings.TYPE_CHECKING:
    from typing import Optional

logger = logging.getLogger(__name__)


def autocomplete(request):
    query = request.GET.get('q', '')
    _items = list()
    if query == '':
        return JsonResponse(_items, safe=False)
    """
    deckitem__id = 15273 = Пакеты (не актиный товар, но доступный для продажи в рознице)
    """
    items = Item.objects.filter(Q(active=True) & Q(deckitem__active=True) | Q(deckitem__id=15273)).filter(
        Q(deckitem__title__istartswith=query) | Q(barcode=query)
    ).distinct().values_list('id', 'deckitem__title', 'deckitem__producer__title', 'weight')[:15]
    _ids = set()
    for item in items:
        name = u'{} - {} - {}'.format(item[1], item[2], item[3])
        _items.append({'name': name, 'id': item[0]})
        _ids.add(item[0])
    if len(_items) < 15:
        items = Item.objects.filter(Q(active=True) & Q(deckitem__active=True)).filter(
            Q(deckitem__title__icontains=query)
        ).distinct().values_list('id', 'deckitem__title', 'deckitem__producer__title', 'weight')[:15 - len(_items)]
        for item in items:
            name = u'{} - {} - {}'.format(item[1], item[2], item[3])
            if item[0] not in _ids:
                _items.append({'name': name, 'id': item[0]})
                _ids.add(item[0])
    return JsonResponse(_items, safe=False)


def autocomplete_customers(request):
    query = request.GET.get('q', '')
    _customers = list()
    if query == '':
        return JsonResponse(_customers, safe=False)
    new_phone = ""
    for char in query:
        if is_digit(char):
            new_phone += char
    if len(new_phone) != 0:
        if new_phone[0] == "8":
            new_phone = new_phone[1:]
    else:
        new_phone = -1
    customers = Account.objects.filter(
        Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(username__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=new_phone)
    ).distinct().values_list('id', 'first_name', 'last_name', 'email', 'phone', 'sale')[:15]
    for customer in customers:
        name = u'{} {}'.format(customer[1], customer[2])
        sale = 0
        if customer[5]:
            sale = (1 - float(customer[5])) * 100
            sale = round(sale)
        _customers.append({'name': name, 'id': customer[0], 'email': customer[3], 'phone': customer[4], 'sale': sale})
    return JsonResponse(_customers, safe=False)


def add_item_to_cart(request):
    cart = request.session.get('cart', list())
    if type(cart) is dict:
        cart = list()
    _id = request.GET.get('id')
    amount = request.GET.get('amount', 1)
    if amount == '':
        amount = 1
    item = Item.objects.filter(id=int(_id)).first()  # type: Item
    for cart_item in cart:
        if int(cart_item.get('id')) == item.id:
            new_amount = int(cart_item.get('amount', 1)) + int(amount)
            cart_item['amount'] = new_amount
            request.session['cart'] = cart
            return JsonResponse({})
    try:
        itemphoto = item.deckitem.itemphoto_set.all().first()
        img_url = itemphoto.thumbnail.url
    except MissingSource:
        img_url = ""
    except AttributeError:
        img_url = ""

    sale_cost = item.current_price()
    if item.current_sale_price():
        sale_cost = item.current_sale_price()
    sale = 0
    if item.get_sale():
        sale = item.get_sale()
    item_dict = {
        'img_url': img_url,
        'cost': item.current_price(),
        'sale': sale,
        'sale_cost': sale_cost,
        'weight': item.weight,
        'id': item.id,
        'amount': amount,
        'title': item.deckitem.title,
    }
    cart.append(item_dict)
    request.session['cart'] = cart
    return JsonResponse({})


def remove_from_cart(request):
    cart = request.session.get('cart', list())
    _id = request.GET.get('id')
    for cart_item in cart:
        if int(cart_item.get('id')) == int(_id):
            cart.remove(cart_item)
            request.session['cart'] = cart
            return JsonResponse({})
    return JsonResponse({})


def update_cart(request):
    user_acc = request.GET.get('user_id', '')
    percent = 0
    user = None  # type: Optional[Account]
    if user_acc != "":
        user = Account.objects.filter(id=int(user_acc)).first()
        if user.sale:
            percent = int(100 - float(user.sale) * 100)
    cart = request.session.get('cart', list())
    full_cost = 0
    sale_cost = 0
    for cart_item in cart:
        item = Item.objects.filter(id=cart_item.get("id")).first()  # type: Item
        cost = float(cart_item.get('cost'))
        amount = int(cart_item.get('amount'))
        sale = cart_item.get('sale')
        if sale:
            sale_cost += cost * amount / 100 * sale
        elif percent:
            if item.id != 23330 and item.id != 23329:
                sale_cost += cost * amount / 100 * percent
                cart_item["sale_cost"] = item.current_price() * user.sale
                cart_item["sale"] = percent
        full_cost += cost * amount
    sale_cost = round(sale_cost, 2)
    result = full_cost - sale_cost
    try:
        cents = float("0.{}".format(str(result).split(".")[1]))
        cents = round(cents, 2)
    except:
        cents = 0
    result -= cents
    response = {'cart': cart, 'cart_sum': full_cost, 'sale_cost': sale_cost, 'result': result, 'cents': cents}
    return JsonResponse(response)


def clear_cart(request):
    cart = list()
    request.session['cart'] = cart
    return redirect('/k/')
