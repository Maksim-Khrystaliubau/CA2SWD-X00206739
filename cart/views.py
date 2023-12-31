from decimal import Decimal

import stripe
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import redirect, render, get_object_or_404

from order.models import Order, OrderItem
from shop.models import Product
from vouchers.forms import VoucherApplyForm
from vouchers.models import Voucher
from .models import Cart, CartItem


def _cart_id(request):
    cart_id = request.session.session_key
    if not cart_id:
        request.session.save()
        cart_id = request.session.session_key
    return cart_id


def add_cart(request, product_id):
    product = Product.objects.get(id=product_id)

    try:
        cart = Cart.objects.get(cart_id=_cart_id(request))
    except Cart.DoesNotExist:
        cart = Cart.objects.create(cart_id=_cart_id(request))
        cart.save()

    try:
        cart_item = CartItem.objects.get(product=product, cart=cart)
        if cart_item.quantity < cart_item.product.stock:
            cart_item.quantity += 1
            cart_item.save()
    except CartItem.DoesNotExist:
        cart_item = CartItem.objects.create(product=product, quantity=1, cart=cart)

    return redirect('cart:cart_detail')


def cart_detail(request, total=0, counter=0, cart_items=None):
    discount = 0
    voucher_id = 0
    new_total = 0
    voucher = None

    try:
        cart = Cart.objects.get(cart_id=_cart_id(request))
        cart_items = CartItem.objects.filter(cart=cart, active=True)

        for cart_item in cart_items:
            total += (cart_item.product.price * cart_item.quantity)
            counter += cart_item.quantity
    except ObjectDoesNotExist:
        pass

    stripe.api_key = settings.STRIPE_SECRET_KEY
    stripe_total = int(total * 100)
    description = 'Online Shop - New Order'
    data_key = settings.STRIPE_PUBLISHABLE_KEY
    voucher_apply_form = VoucherApplyForm()

    try:
        voucher_id = request.session.get('voucher_id')
        voucher = Voucher.objects.get(id=voucher_id)
        if voucher:
            discount = (total * (voucher.discount / Decimal('100')))
            new_total = (total - discount)
            stripe_total = int(new_total * 100)
    except ObjectDoesNotExist:
        pass

    # Updated code to handle both authenticated and anonymous users
    if request.user.is_authenticated:
        email_address = request.user.email
    else:
        email_address = None  # or any default value you want to set for anonymous users

    if request.method == 'POST':
        try:
            # ... (rest of your code for handling stripe payment)

            # Creating the order
            try:
                order_details = Order.objects.create(
                    emailAddress=email_address,
                    # ... (other fields as needed)
                )
                order_details.save()
                if voucher:
                    order_details.total = new_total
                    order_details.voucher = voucher
                    order_details.discount = discount
                    order_details.save()

                for cart_item in cart_items:
                    oi = OrderItem.objects.create(
                        order=order_details,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price=cart_item.product.price,
                    )
                    if voucher != None:
                        discount = (oi.price * (voucher.discount / Decimal('100')))
                        oi.price = (oi.price - discount)
                    else:
                        oi.price = oi.price * oi.quantity
                    oi.save()

                    # Reduce stock when the order is placed or saved
                    products = Product.objects.get(id=cart_item.product.id)
                    products.stock = int(cart_item.product.stock - cart_item.quantity)
                    products.save()
                    cart_item.delete()

                return redirect('order:thanks', order_details.id)
            except ObjectDoesNotExist:
                pass

        except stripe.error.CardError as e:
            return e

    return render(request, 'cart.html', {
        'cart_items': cart_items,
        'total': total,
        'counter': counter,
        'data_key': data_key,
        'stripe_total': stripe_total,
        'description': description,
        'voucher_apply_form': voucher_apply_form,
        'new_total': new_total,
        'voucher': voucher,
        'discount': discount
    })


def cart_remove(request, product_id):
    cart = Cart.objects.get(cart_id=_cart_id(request))
    product = get_object_or_404(Product, id=product_id)
    cart_item = CartItem.objects.get(product=product, cart=cart)

    if cart_item.quantity > 1:
        cart_item.quantity -= 1
        cart_item.save()
    else:
        # Handle the case where quantity is 1
        cart_item.delete()  # or cart_item.active = False

    return redirect('cart:cart_detail')


def full_remove(request, product_id):
    try:
        cart = Cart.objects.get(cart_id=_cart_id(request))
        product = Product.objects.get(id=product_id)
        cart_item = CartItem.objects.get(product=product, cart=cart)
        cart_item.delete()
        return redirect('cart:cart_detail')
    except (Cart.DoesNotExist, Product.DoesNotExist, CartItem.DoesNotExist):
        raise Http404("The requested product or cart item does not exist.")
