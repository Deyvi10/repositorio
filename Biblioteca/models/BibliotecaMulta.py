from odoo import models, fields, api
from odoo.exceptions import ValidationError

class BibliotecaMulta(models.Model):
    _name = 'biblioteca.multa'
    _description = 'Multa a Usuario'
    _rec_name = 'display_name'

    usuario_id = fields.Many2one(comodel_name='biblioteca.usuario', string='Usuario', required=True)
    monto = fields.Float(string='Monto', required=True)
    motivo = fields.Selection(
        [('re', 'Retraso'), 
         ('da', 'Daño'), 
         ('pe', 'Pérdida')],
        string='Motivo', required=True
    )
    fecha = fields.Date(string='Fecha', required=True)
    estado = fields.Selection(
        [('pen', 'Pendiente'), 
         ('pa', 'Pagado')],
        string='Estado',required=True, default='pen'
    )
    prestamo = fields.Many2one('biblioteca.prestamo')
    
    @api.constrains('motivo')
    def _motivo(self):
        for record in self:
            motivos = [m.strip() for m in record.motivo.split(',')]
            if 'da' in motivos and 'pe' in motivos:
                raise ValidationError("No puedes seleccionar 'Daño' y 'Pérdida' al mismo tiempo.")