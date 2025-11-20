from odoo import models, fields, api
from odoo.exceptions import ValidationError
import requests

class BibliotecaLibro(models.Model):
    _name = 'biblioteca.libro'
    _description = 'Libro de la Biblioteca'
    _rec_name = 'name'

    name = fields.Char(string='Título del Libro', required=False)
    author_id = fields.Many2one('biblioteca.autor', string='Autor')
    isbn = fields.Char(string='ISBN', required=False)
    editorial_id = fields.Many2one('biblioteca.editorial', string='Editorial')
    fechapubli = fields.Integer(string='Año de publicación')
    genero_id = fields.Many2one('biblioteca.genero', string='Género o Categoría')
    numpaginas = fields.Integer(string='Número de páginas', default=0)
    disponi = fields.Selection(
        [('disponible', 'Disponible'), ('prestado', 'Prestado'), ('reservado', 'Reservado')],
        string='Estado', default='disponible')
    ubicacion_id = fields.Many2one('biblioteca.ubicacion', string='Ubicación física')
    ejemplares = fields.Integer(string='Número de ejemplares', default=1)
    costo = fields.Float(compute="_compute_costo", store=True, string='Costo')
    description = fields.Text(string='Resumen')

    @api.depends('ejemplares')
    def _compute_costo(self):
        for record in self:
            record.costo = (record.ejemplares or 0) / 100
            
    def action_importar_libro(self):
        for record in self:
            if not record.isbn:
                raise ValidationError("Debes ingresar un ISBN antes de importar.")
            record.importar_libro_por_isbn(record.isbn)

    @api.model
    def importar_libro_por_isbn(self, isbn):
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        response = requests.get(url)
        data = response.json()

        libro_data = data.get(f"ISBN:{isbn}")
        if not libro_data:
            raise ValidationError("No se encontró información para este ISBN en OpenLibrary.")

        titulo = libro_data.get('title', 'Sin título')

        autores = libro_data.get('authors', [])
        autor_nombre = autores[0]['name'] if autores else 'Autor desconocido'
        autor_split = autor_nombre.split()
        firstname = autor_split[0] if autor_split else 'Nombre'
        lastname = ' '.join(autor_split[1:]) if len(autor_split) > 1 else 'Apellido'
        autor = self.env['biblioteca.autor'].search([
            ('firstname', '=', firstname),
            ('lastname', '=', lastname)
        ], limit=1)
        if not autor:
            autor = self.env['biblioteca.autor'].create({
                'firstname': firstname,
                'lastname': lastname,
                'nacionalidad': 'Desconocida'
            })

        generos = libro_data.get('subjects', [])
        genero_nombre = generos[0]['name'] if generos else 'General'
        genero = self.env['biblioteca.genero'].search([('genero', '=', genero_nombre)], limit=1)
        if not genero:
            genero = self.env['biblioteca.genero'].create({
                'genero': genero_nombre,
                'descripcion': 'Importado desde OpenLibrary'
            })

        fecha_publi = libro_data.get('publish_date', '')
        try:
            fechapubli = int(fecha_publi[-4:]) if fecha_publi else 0
        except:
            fechapubli = 0

        paginas = libro_data.get('number_of_pages', 0)

        resumen = libro_data.get('notes', '')

        nuevo_libro = self.write({
            'name': titulo,
            'isbn': isbn,
            'author_id': autor.id,
            'genero_id': genero.id,
            'fechapubli': fechapubli,
            'numpaginas': paginas,
            'description': resumen,
        })

        return nuevo_libro