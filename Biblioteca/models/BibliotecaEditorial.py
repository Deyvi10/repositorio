from odoo import models, fields, api

class BibliotecaEditorial(models.Model):
    _name = 'biblioteca.editorial'
    _description = 'Editorial de la Biblioteca'
    _rec_name = 'display_name'

    editorial = fields.Char(string='Nombre')
    display_name = fields.Char(compute='_compute_display_name', store=True)
    ciudad = fields.Char(string='Ciudad o País')
    fundacion = fields.Integer(string='Año de fundación')
    libro_ids = fields.One2many('biblioteca.libro', 'editorial_id', string='Libros publicados')

    @api.depends('editorial')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.editorial or ''