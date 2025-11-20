from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
         
class BibliotecaPrestamo(models.Model):
    _name = 'biblioteca.prestamo'
    _description = 'Prestamo de libro'
    _rec_name = 'name'

    name = fields.Char(string="Código Prestamo")
    usuario_id = fields.Many2one('biblioteca.usuario', string='Usuario', required=True)
    libro_id = fields.Many2many('biblioteca.libro', string='Libro', required=True)
    fechaprestamo = fields.Datetime(default=datetime.now(), string='Fecha de préstamo')
    fechadevolucion = fields.Date(string='Fecha de devolución')
    estado = fields.Selection([
        ('b', 'Borrador'),
        ('p', 'Préstamo'),
        ('m', 'Multa'),
        ('d', 'Devuelto'),
    ], string='Estado', default='b')
    observaciones=fields.Char(string='Observaciones')
    multabool = fields.Boolean(default=False)
    multa = fields.Float(string='Monto de multa')
    multa_id = fields.One2many('biblioteca.multa', 'prestamo', string='Multa')
    motivo_multa = fields.Selection([
        ('re', 'Retraso'),
        ('da', 'Daño'),
        ('pe', 'Pérdida'),
    ], string='Motivo de multa')

    fechamax = fields.Datetime(compute='_compute_fecha_devo', string='Fecha máxima de devolución', store=True)
    personalprestamo = fields.Many2one('biblioteca.personal', string='Personal de préstamo')

    def action_aplicar_multa(self):
        """Cambia estado a multa y crea registro en biblioteca.multa."""
        for prestamo in self:
            if prestamo.estado == 'm':
                continue

            monto = 0.0
            if prestamo.motivo_multa == 're':
                monto = 2.0
            elif prestamo.motivo_multa == 'da':
                monto = 4.0
            elif prestamo.motivo_multa == 'pe':
                monto = 6.0

            prestamo.write({
                'estado': 'm',
                'multabool': True,
                'multa': monto,
            })

            self.env['biblioteca.multa'].create({
                'usuario_id': prestamo.usuario_id.id,
                'monto': monto,
                'motivo': prestamo.motivo_multa or 're',
                'fecha': datetime.now().date(),
                'estado': 'pen',
                'prestamo': prestamo.id,
            })

    def _cron_multas(self):
        pass

    @api.depends('fechaprestamo')
    def _compute_fecha_devo(self):
        for record in self:
            record.fechamax = record.fechaprestamo + timedelta(days=2) if record.fechaprestamo else False

    def generar_prestamo(self):
        self.write({'estado': 'p'})

    def write(self, vals):
        if 'name' not in vals or not vals['name']:
            seq = self.env.ref('biblioteca.sequence_codigo_prestamo').next_by_code('biblioteca.prestamo')
            vals['name'] = seq
        return super(BibliotecaPrestamo, self).write(vals)
    
    def create(self, vals):
        if not vals.get('libro_id'):
            raise ValidationError("Seleccione un libro antes de prestar")
        return super(BibliotecaPrestamo, self).create(vals)

    def generar_prestamo(self):
        print("generando Prestamo")
        self.write({'estado': 'p'})
        
    def devolver(self):
        return{
            'type': 'ir.actions.act_window',
            'res_model': 'biblioteca.wizard',
            'view_mode': 'form',
            'target': 'new',
            'view_id': self.env.ref('biblioteca.biblioteca_wizard_form').id,
            'context': {'default_prestamo_id': self.id}
        }
            
    @api.depends('fechaprestamo')
    def _compute_fecha_devo(self):
        for record in self:
            if record.fechaprestamo:
                record.fechamax = record.fechaprestamo + timedelta(days=2)
            else:
                record.fechamax = False

#    @api.depends('libro_id', 'usuario_id')
#    def _compute_display_name(self):
#        for record in self:
#            record.display_name = f"{record.libro_id.name or ''} - {record.usuario_id.nombre or ''}"