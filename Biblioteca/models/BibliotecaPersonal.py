from odoo import models, fields, api
                        
class BibliotecaPersonal(models.Model):
    _name = 'biblioteca.personal'
    _description = 'Personal de la Biblioteca'
    _rec_name = 'display_name'

    empleado = fields.Char(string='Nombre del empleado')
    cargo = fields.Selection([
        ('bibliotecario', 'Bibliotecario'),
        ('auxiliar', 'Auxiliar'),
        ('otro', 'Otro')
    ], string='Cargo')
    fechaingreso = fields.Date(string='Fecha de ingreso')
    contacto = fields.Char(string='Contacto')  

    @api.depends('empleado')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.empleado or ''