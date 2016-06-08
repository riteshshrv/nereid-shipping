# -*- coding: utf-8 -*-
"""
    test_checkout

    :copyright: (c) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for details.
"""
import os
import json
import unittest
from mock import patch
from decimal import Decimal

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.config import config
from trytond.transaction import Transaction
from trytond import backend

from trytond.modules.nereid_cart_b2c.tests.test_product import BaseTestCase

config.set('email', 'from', 'from@xyz.com')


class BaseTestCheckout(BaseTestCase):
    """Test Checkout Base"""

    @classmethod
    def setUpClass(cls):
        print "====== Tests are running on %s ========" % backend.name()

    def setUp(self):
        super(BaseTestCheckout, self).setUp()
        trytond.tests.test_tryton.install_module('nereid_shipping')
        trytond.tests.test_tryton.install_module('shipping_ups')

        self.Carrier = POOL.get('carrier')
        self.Category = POOL.get('product.category')
        self.Account = POOL.get('account.account')
        self.ProductTemplate = POOL.get('product.template')

        self.templates.update({
            'checkout/signin.jinja': '{{form.errors|safe}}',
            'checkout/signin-email-in-use.jinja': '{{email}} in use',
            'checkout/shipping_address.jinja': '{{address_form.errors|safe}}',
            'checkout/billing_address.jinja': '{{address_form.errors|safe}}',
            'checkout/delivery_method.jinja':
                '{{delivery_rates|map(attribute=4)|list|tojson|safe}}',
            'checkout/payment_method.jinja': '''[
                {{payment_form.errors|safe}},
                {{credit_card_form.errors|safe}},
            ]''',
            'emails/sale-confirmation-text.jinja': ' ',
            'emails/sale-confirmation-html.jinja': ' ',
            'checkout.jinja': '{{form.errors|safe}}',
            'sale.jinja': ' ',
            'sales.jinja': '''{{request.args.get('filter_by')}}
                {% for sale in sales %}#{{sale.id}}{% endfor %}
            '''
        })

        # Patch SMTP Lib
        self.smtplib_patcher = patch('smtplib.SMTP')
        self.PatchedSMTP = self.smtplib_patcher.start()

    def setup_defaults(self):
        """
        Setup the defaults
        """
        super(BaseTestCheckout, self).setup_defaults()

        Address = POOL.get('party.address')
        StockLocation = POOL.get('stock.location')

        # Add emails to party
        self.Party.write([self.registered_user.party], {
            'contact_mechanisms': [('create', [
                {'type': 'email', 'value': 'test@ol.in'},
            ])],
        })

        self.Party.write([self.registered_user2.party], {
            'contact_mechanisms': [('create', [
                {'type': 'email', 'value': 'test2@ol.in'},
            ])],
        })
        # Create default addresses
        Address.create([
            {
                'party': self.registered_user.party.id,
                'name': self.registered_user.party.name,
            }, {
                'party': self.registered_user2.party.id,
                'name': self.registered_user2.party.name,
            },
        ])

        self.country, = self.Country.create([{
            'name': 'United States of America',
            'code': 'US',
        }])

        self.subdivision, = self.Subdivision.create([{
            'country': self.country.id,
            'name': 'California',
            'code': 'US-CA',
            'type': 'state',
        }])

        self.subdivision_fl, = self.Subdivision.create([{
            'country': self.country.id,
            'name': 'Florida',
            'code': 'US-FL',
            'type': 'state',
        }])

        website, = self.NereidWebsite.search([])
        website.countries = list(website.countries) + [self.country]
        website.save()

        self.uom, = self.Uom.search([('symbol', '=', 'cm')])

        self.product = self.create_product()
        carrier_product = self.create_product('service')

        # Create party
        carrier_party, = self.Party.create([{
            'name': 'Test Party',
        }])

        self.carrier, = self.Carrier.create([{
            'party': carrier_party.id,
            'carrier_product': carrier_product.id,
            'carrier_cost_method': 'ups',
            'ups_license_key': os.environ['UPS_LICENSE_NO'],
            'ups_user_id': os.environ['UPS_USER_ID'],
            'ups_password': os.environ['UPS_PASSWORD'],
            'ups_shipper_no': os.environ['UPS_SHIPPER_NO'],
            'ups_is_test': True,
            'ups_uom_system': '01',
            'currency': self.company.currency.id,
        }])

        warehouse_address, = Address.create([{
            'name': 'Fulfil.IO',
            'party': self.company.party.id,
            'street': '247 High Street',
            'zip': '94301-1041',
            'city': 'Palo Alto',
            'country': self.country.id,
            'subdivision': self.subdivision.id,
        }])

        warehouse = StockLocation.search([('type', '=', 'warehouse')])[0]
        warehouse.address = warehouse_address
        warehouse.save()

        # UPS rrequired phone no. for shipper address
        self.Party.write([self.company.party], {
            'vat_number': '123456',
            'contact_mechanisms': [('create', [
                {'type': 'phone', 'value': '+1650786543'},
            ])],
        })

    def create_product(self, type='goods'):
        """
        Create product
        """
        # Create product category
        category, = self.Category.create([{
            'name': 'Test Category',
        }])

        account_revenue, = self.Account.search([
            ('kind', '=', 'revenue')
        ])

        values = {
            'name': 'Test Product',
            'category': category.id,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'type': type,
            'sale_uom': self.uom,
            'default_uom': self.uom,
            'salable': True,
            'account_revenue': account_revenue.id,
            'products': [
                ('create', [{
                    'code': 'Test Product',
                    'uri': 'test-product',
                }])
            ]
        }
        if type == 'goods':
            self.uom_kg, = self.Uom.search([('symbol', '=', 'kg')])
            values['products'][0][1][0].update({
                'weight': .5,
                'weight_uom': self.uom_kg.id,
            })

        # Create product
        template, = self.ProductTemplate.create([values])

        return template.products[0]

    def _create_pricelists(self):
        """
        Create the pricelists
        """
        # Setup the pricelists
        self.party_pl_margin = Decimal('1')
        self.guest_pl_margin = Decimal('1')
        user_price_list, = self.PriceList.create([{
            'name': 'PL 1',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.party_pl_margin
                }])
            ],
        }])
        guest_price_list, = self.PriceList.create([{
            'name': 'PL 2',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.guest_pl_margin
                }])
            ],
        }])
        return guest_price_list.id, user_price_list.id

    def tearDown(self):
        # Unpatch SMTP Lib
        self.smtplib_patcher.stop()


class TestCheckoutDeliveryMethod(BaseTestCheckout):
    "Test the Delivery Method Step"

    def test_0005_no_skip_signin(self):
        "Ensure that guest orders cant directly skip to enter delivery method"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )
                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/sign-in')
                )

    def test_0010_skip_if_no_weight(self):
        "Ensure that no delivery method selection if no shipment weight"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Redirect to shipping address since there is no address
                # and shipment method cant be selected without a delivery
                # address
                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': '33137',
                        'city': 'Miami',
                        'phone': '8888888888',
                        'country': self.country.id,
                        'subdivision': self.subdivision_fl.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)

                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                # TODO: pay fully

    def test_0015_no_skip_if_weight(self):
        "Ensure that delivery method selection if shipment weight"
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post(
                    '/cart/add', data={
                        'product': self.product.id, 'quantity': 5
                    }
                )

                # Sign-in
                rv = c.post(
                    '/checkout/sign-in', data={
                        'email': 'new@example.com',
                        'checkout_mode': 'guest',
                    }
                )

                # Redirect to shipping address since there is no address
                # and shipment method cant be selected without a delivery
                # address
                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/shipping-address')
                )
                rv = c.post(
                    '/checkout/shipping-address',
                    data={
                        'name': 'Sharoon Thomas',
                        'street': 'Biscayne Boulevard',
                        'streetbis': 'Apt. 1906, Biscayne Park',
                        'zip': '33137',
                        'city': 'Miami',
                        'phone': '8888888888',
                        'country': self.country.id,
                        'subdivision': self.subdivision_fl.id,
                    }
                )
                self.assertEqual(rv.status_code, 302)

                rv = c.get('/checkout/delivery-method')
                self.assertEqual(rv.status_code, 200)
                rv_json = json.loads(rv.data)
                self.assertTrue(len(rv_json) > 1)

                rv = c.post(
                    '/checkout/delivery-method',
                    data={'carrier_json': json.dumps(rv_json[0])}
                )
                self.assertEqual(rv.status_code, 302)
                self.assertTrue(
                    rv.location.endswith('/checkout/payment')
                )
                sale, = self.Sale.search([])
                # Product line + shipping line
                self.assertEqual(len(sale.lines), 2)
                for line in sale.lines:
                    self.assertTrue(line.amount)
                self.assertEqual(sale.carrier, self.carrier)


def suite():
    "Checkout test suite"
    "Define suite"
    test_suite = trytond.tests.test_tryton.suite()
    loader = unittest.TestLoader()
    test_suite.addTests(
        loader.loadTestsFromTestCase(TestCheckoutDeliveryMethod)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
