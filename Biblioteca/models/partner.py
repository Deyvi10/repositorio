from odoo import models, fields, api
from odoo.exeptions import ValidationError

class Partner(models.Model):
    _inherit= 'res.partner'
    
    nacinalidad=fields.Char(string='nacionalidad')
    fecha_nacimiento=fields.Datetime(string='Fecha de nacimiento')
    sexo= fields.Selection([('m':'masculino'),
                            ('f':'femenino'),
                            ('o':'otros')], string='Sexo')