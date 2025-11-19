# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class AgreementCustomerPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'agreement_count' in counters:
            domain = self._get_agreement_portal_domain()
            agreement_model = request.env['rmc.contract.agreement'].sudo()
            values['agreement_count'] = agreement_model.search_count(domain)
        return values

    def _get_agreement_portal_domain(self):
        user = request.env.user
        if user.has_group('rmc_manpower_contractor.group_rmc_manager'):
            return []
        return [('contractor_id', '=', user.partner_id.id)]

    @http.route(['/my/agreements', '/my/agreements/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_agreements(self, page=1, sortby='date_desc', **kw):
        values = self._prepare_portal_layout_values()
        domain = self._get_agreement_portal_domain()

        searchbar_sortings = {
            'date_desc': {'label': _('Newest'), 'order': 'create_date desc'},
            'date_asc': {'label': _('Oldest'), 'order': 'create_date asc'},
            'name': {'label': _('Reference'), 'order': 'name asc'},
            'state': {'label': _('Status'), 'order': 'state asc, create_date desc'},
        }
        if sortby not in searchbar_sortings:
            sortby = 'date_desc'
        order = searchbar_sortings[sortby]['order']

        agreement_model = request.env['rmc.contract.agreement'].sudo()
        agreement_count = agreement_model.search_count(domain)
        pager = portal_pager(
            url='/my/agreements',
            total=agreement_count,
            page=page,
            step=self._items_per_page,
        )
        agreements = agreement_model.search(
            domain,
            order=order,
            limit=self._items_per_page,
            offset=pager['offset'],
        )

        values.update({
            'agreements': agreements,
            'pager': pager,
            'page_name': 'agreement_portal_list',
            'default_url': '/my/agreements',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        return request.render('rmc_manpower_contractor.portal_my_agreements', values)


class AgreementPortalController(http.Controller):

    @http.route(['/contract/agreement/<int:agreement_id>'], type='http', auth='public', website=True)
    def agreement_portal(self, agreement_id, **kw):
        """
        Dynamic web agreement portal
        Shows contract details with conditional sections based on contract_type
        """
        try:
            agreement = request.env['rmc.contract.agreement'].sudo().browse(agreement_id)
            
            if not agreement.exists():
                return request.render('website.404')
            
            # Check access
            if request.env.user._is_public():
                # Public access allowed for preview
                pass
            elif request.env.user.partner_id != agreement.contractor_id:
                # Portal user must be the contractor
                if not request.env.user.has_group('rmc_manpower_contractor.group_rmc_manager'):
                    raise AccessError(_('You do not have access to this agreement.'))
            
            values = {
                'agreement': agreement,
                'page_name': 'agreement_portal',
            }
            
            return request.render('rmc_manpower_contractor.agreement_portal_template', values)
        
        except AccessError:
            return request.render('website.403')
        except Exception as e:
            return request.render('website.404')

    @http.route(['/contract/agreement/<int:agreement_id>/send_for_sign'], type='http', auth='user', website=True, csrf=False)
    def agreement_send_for_sign(self, agreement_id, **kw):
        """Send agreement for signature"""
        try:
            agreement = request.env['rmc.contract.agreement'].sudo().browse(agreement_id)

            if not agreement.exists():
                raise AccessError(_('The requested agreement no longer exists.'))
            
            # Check access
            if not request.env.user.has_group('rmc_manpower_contractor.group_rmc_manager'):
                if request.env.user.partner_id != agreement.contractor_id:
                    raise AccessError(_('You do not have permission to perform this action.'))
            
            agreement.action_send_for_sign()
            
            return request.redirect(f'/contract/agreement/{agreement_id}?message=sign_sent')
        
        except UserError as e:
            return request.redirect(f'/contract/agreement/{agreement_id}?error={e.args[0]}')
        except Exception as e:
            return request.redirect(f'/contract/agreement/{agreement_id}?error=An error occurred')
