from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError



class OperationalRequest(models.Model):
    _name = 'enterprise.ops.request'
    _description = 'Operational Request'
    _order = 'id desc'
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    # Real sequence-based numbering (REQ/2026/00001 etc.) comes in T14.
    # For now, default is the literal string "New" so the record is
    # still creatable/savable without a sequence dependency.

    # ------------------------------------------------------------------
    # Who / Where
    # ------------------------------------------------------------------
    employee_id = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        required=True,
        index=True,
        default=lambda self: self.env.user,
    )
    department_id = fields.Many2one(
        comodel_name='enterprise.ops.department',
        string='Department',
        required=True,
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    # ------------------------------------------------------------------
    # Request details
    # ------------------------------------------------------------------
    priority = fields.Selection(
        selection=[
            ('0', 'Normal'),
            ('1', 'High'),
            ('2', 'Urgent'),
        ],
        string='Priority',
        default='0',
        required=True,
    )
    request_date = fields.Date(
        string='Request Date',
        required=True,
        default=fields.Date.context_today,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
    )

    #  Workflow state
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('procurement', 'Procurement'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        index=True,
    )

    active = fields.Boolean(string='Active', default=True)

    line_ids = fields.One2many(
        comodel_name='enterprise.ops.request.line',
        inverse_name='request_id',
        string='Request Lines',
        copy=True,
    )

    currency_id = fields.Many2one(
        string = 'Currency',
        related = 'company_id.currency_id',
        store = True,
        readonly =True
    )

        # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    amount_lines_total = fields.Monetary(
        string='Lines Total',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=True,
    )
    amount_additional_charges = fields.Monetary(
        string='Additional Charges',
        currency_field='currency_id',
        default=0.0,
    )
    amount_total = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        compute='_compute_amounts',
        inverse='_inverse_amount_total',
        store=True,
    )

   

    @api.depends('line_ids.subtotal', 'amount_additional_charges')
    def _compute_amounts(self):
        for request in self:
            request.amount_lines_total = sum(request.line_ids.mapped('subtotal'))
            request.amount_total = request.amount_lines_total + request.amount_additional_charges

    def _inverse_amount_total(self):
        for request in self:
            request.amount_additional_charges = request.amount_total - request.amount_lines_total

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if(self.department_id and self.department_id.company_id != self.company_id):
            self.department_id = False

    @api.constrains('reason')
    def _check_reason_not_blank(self):
        for request in self:
            if not request.reason or not request.reason.strip():
                raise ValidationError(_("Reason cannot be empty or contain only whitespace"))


    @api.constrains('department_id', 'company_id')
    def _check_department_company_match(self):
        for request in self:
            if (request.department_id
                    and request.department_id.company_id != request.company_id):
                raise ValidationError(_(
                    "Department '%(dept)s' belongs to company '%(dept_company)s', "
                    "which does not match this request's company '%(company)s'.",
                    dept=request.department_id.name,
                    dept_company=request.department_id.company_id.name,
                    company=request.company_id.name,
                ))


    _TRANSITION = {
        'submitted':{'from':('draft',)},
        'approved':{'from':('submitted',)},
        'rejected':{'from':('submitted',)},
        'procurement':{'from':('approved',)},
        'done':{'from':('procurement',)},
        'cancelled':{'from':('draft','submitted','approved','procurement')},
        'draft':{'from':('cancelled','rejected')}


    }

    def _apply_transition(self,target_state):
        allowed_from = self._TRANSITION[target_state]['from']
        invalid = self.filtered(lambda r:r.state not in allowed_from)
        if invalid:
            raise UserError(_(
                "Cannot move %(names)s to '%(target)s'. "
                "Current state does not allow this transition.",
                names=', '.join(invalid.mapped('display_name')),
                target=target_state,
            ))

        self.write({'state':target_state})


    def action_submit(self):
        empty = self.filtered(lambda r: not r.line_ids)
        if empty:
            raise UserError(_(
                "Cannot submit %(names)s: at least one line is required.",
                names=', '.join(empty.mapped('display_name')),
            ))
        self._apply_transition('submitted')

    def action_approve(self):
        self._apply_transition('approved')

    def action_reject(self):
        self._apply_transition('rejected')

    def action_send_to_procurement(self):
        self._apply_transition('procurement')

    def action_done(self):
        self._apply_transition('done')

    def action_cancel(self):
        self._apply_transition('cancelled')

    def action_reset_draft(self):
        self._apply_transition('draft')

    




                    
        


    

    

    

    
