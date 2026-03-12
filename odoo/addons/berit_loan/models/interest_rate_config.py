# -*- coding: utf-8 -*-
from odoo import models, fields

class InterestRateConfig(models.Model):
    _name = 'berit.interest.rate.config'
    _description = 'Interest Rate Configuration'
    _order = 'min_amount'

    min_amount = fields.Float(
        string='Minimum Amount',
        required=True,
        help='Minimum loan amount for this interest rate tier'
    )
    max_amount = fields.Float(
        string='Maximum Amount',
        help='Maximum loan amount for this interest rate tier (0 = no limit)'
    )
    interest_rate = fields.Float(
        string='Interest Rate (%)',
        required=True,
        help='Monthly interest rate percentage'
    )
    description = fields.Char(
        string='Description',
        required=True,
        help='Description of this interest rate tier'
    )

    def get_interest_rate_for_amount(self, amount):
        """Get the applicable interest rate for a given loan amount"""
        for config in self.search([('min_amount', '<=', amount)], order='min_amount desc'):
            if config.max_amount == 0 or amount <= config.max_amount:
                return config.interest_rate
        return 0.0
