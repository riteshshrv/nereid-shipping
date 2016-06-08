# -*- coding: utf-8 -*-
"""
    website

    :copyright: (c) 2016 by Fulfil.IO Inc.
    :license: see LICENSE for details.
"""
from trytond.pool import PoolMeta
from trytond.model import ModelSQL, fields

__metaclass__ = PoolMeta
__all__ = ['Website', 'WebsiteCarrier']


class Website:
    __name__ = 'nereid.website'

    carriers = fields.Many2Many(
        "nereid.website.website-carrier", "website", "carrier", "Carriers"
    )


class WebsiteCarrier(ModelSQL):
    "Website Carrier"
    __name__ = "nereid.website.website-carrier"

    website = fields.Many2One(
        "nereid.website", "Website", ondelete='CASCADE', select=True,
        required=True
    )
    carrier = fields.Many2One(
        "carrier", "Carrier", ondelete='CASCADE', select=True, required=True
    )
