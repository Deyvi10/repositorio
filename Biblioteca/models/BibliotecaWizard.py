from odoo import models, fields

class BibliotecaWizard(models.TransientModel):
    _name = "biblioteca.wizard"
    _description = "Wizard para devolucion de prestamo"
    
    prestamo_id= fields.Many2one('biblioteca.prestamo')
    motivo_multa = fields.Selection([
        ('re', 'Retraso'),
        ('da', 'Daño'),
        ('pe', 'Pérdida'),
    ], string='Motivo de multa', default='re')
    observaciones=fields.Char(string='Observaciones')
    
    def cerrar_prestamo(self):
        self.prestamo_id.motivo_multa = self.motivo_multa
        self.prestamo_id.observaciones = self.observaciones
        self.prestamo_id.estado = 'd'