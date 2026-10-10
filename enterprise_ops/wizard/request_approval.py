from odoo import models, fields
 
class RequestApprovalWizard(models.TransientModel):
    _name = 'enterprise.ops.request.approval'
    _description = 'Request Approval wizard'

    request_ids = fields.Many2many(
        comodel_name='enterprise.ops.request',
        relation='enterprise_ops_request_approval_rel',
        column1='wizard_id',
        column2 = 'request_id',
        required = True

    )

    decision = fields.Selection(
        selection=[('approve','Approve'),('reject','Reject')],
        string='Decision',
        required = True,
    )
    rejection_reason = fields.Text(string='Rejected Reason')

    def action_confirm(self):
        self.ensure_one()

        if self.decision =='approve':
            self.request_ids.action_approve()

        else:
            self.request_ids.action_reject(reason = self.rejection_reason)
        return {'type':'ir.actions.act_window_close'}