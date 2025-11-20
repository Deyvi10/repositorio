from odoo import models, fields, api
from odoo.exceptions import ValidationError
                      
class BibliotecaUsuario(models.Model):
    _name = 'biblioteca.usuario'
    _description = 'Usuario de Biblioteca'
    _rec_name = 'display_name'

    nombre = fields.Char(string='Nombre completo', required=True )
    dni = fields.Char(string='DNI o Identificación', required=True, size=10)
    cel = fields.Char(string='Teléfono')
    correo = fields.Char(string='Correo electrónico')
    direccion = fields.Char(string='Dirección')
    display_name = fields.Char(compute='_compute_display_name', store=True)
    tipousuario= fields.Selection(selection=[('alumno', 'Alumno'),
                                              ('profesor', 'Profesor'),
                                              ('personal', 'Personal'),
                                              ('externo', 'Usuario externo')],string='Tipo de usuario')
    historialprestamo= fields.Char(string='Historial de prestamo')
    prestamo_ids = fields.One2many(
        comodel_name='biblioteca.prestamo',
        inverse_name='usuario_id',
        string='Historial de préstamos'
    )

    @api.depends('nombre')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.nombre or 'Usuario sin nombre'

    @api.constrains('dni')
    def _check_dni(self):
        for record in self:
            if record.dni:
                es_valido, mensaje = self.validar_cedula(record.dni)
                if not es_valido:
                    raise ValidationError(mensaje)

    def validar_cedula(self, cedula):
        if len(cedula) != 10:
            return (False, "La cédula debe tener exactamente 10 dígitos")
        if not cedula.isdigit():
            return (False, "La cédula solo debe contener números")
        provincia = int(cedula[:2])
        if provincia < 1 or provincia > 24:
            return (False, "Los primeros dos dígitos deben corresponder a una provincia ecuatoriana (01–24)")
        tercer_digito = int(cedula[2])
        if tercer_digito < 0 or tercer_digito > 6:
            return (False, "El tercer dígito debe estar entre 0 y 6")
        coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
        digito_verificador = int(cedula[-1])
        suma = 0
        for i in range(9):
            valor = int(cedula[i]) * coeficientes[i]
            if valor >= 10:
                valor -= 9
            suma += valor
        digito_calculado = (10 - (suma % 10)) % 10
        if digito_calculado != digito_verificador:
            return (False, f"Dígito verificador incorrecto.")
        return (True, "Cédula válida")