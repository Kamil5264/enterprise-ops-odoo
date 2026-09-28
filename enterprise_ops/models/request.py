from odoo import api, fields, models, _


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

    

    

    

    
