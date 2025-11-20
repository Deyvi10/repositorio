from odoo import models, fields, api

class BibliotecaAutor(models.Model):
    _name = 'biblioteca.autor'
    _description = 'Autor de la Biblioteca'
    _rec_name = 'display_name'

    firstname = fields.Char(string='Nombre')
    lastname = fields.Char(string='Apellido')
    nacionalidad = fields.Char(string='Nacionalidad')
    cumpleautor = fields.Date(string='Fecha de nacimiento')
    biografia = fields.Text(string='Biografía')
    display_name = fields.Char(compute='_compute_display_name', store=True)
    book_ids = fields.One2many('biblioteca.libro', 'author_id', string='Libros escritos')

    @api.depends('firstname', 'lastname')
    def _compute_display_name(self):
        for record in self:
            parts = [record.firstname or '', record.lastname or '']
            record.display_name = ' '.join([p for p in parts if p]).strip()