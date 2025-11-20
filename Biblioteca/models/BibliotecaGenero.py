from odoo import models, fields, api

class BibliotecaGenero(models.Model):
    _name = 'biblioteca.genero'
    _description = 'Género o Categoría'
    _rec_name = 'display_name'

    genero = fields.Char(string='Nombre del género', required=True)
    descripcion = fields.Text(string='Descripción breve')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('genero')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.genero or ''