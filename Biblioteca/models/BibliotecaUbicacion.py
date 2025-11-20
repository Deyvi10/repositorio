from odoo import models, fields, api

class BibliotecaUbicacion(models.Model):
    _name = 'biblioteca.ubicacion'
    _description = 'Ubicación Física'
    _rec_name = 'display_name'

    ubicacion = fields.Char(string='Nombre del bloque o sala', required=True)
    descripcion = fields.Text(string='Descripción o referencia física')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('ubicacion')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.ubicacion or ''