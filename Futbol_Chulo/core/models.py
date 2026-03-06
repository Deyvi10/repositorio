from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, time, datetime
from django.db.models import Sum
from django.core.exceptions import ValidationError

# =====================================================
# 1. USUARIOS Y PERFILES
# =====================================================
class Perfil(models.Model):
    ROLES = [
        ('ORG', 'Organizador'),         # Dueño del sistema
        ('VOC', 'Vocal de Mesa'),       # Ayudante
        ('DIR', 'Dirigente de Equipo'), # Cliente Torneo
        ('FAN', 'Aficionado / Cliente'),# Cliente Cancha / Espectador
    ]
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=3, choices=ROLES, default='FAN') 
    telefono = models.CharField(max_length=15, blank=True, null=True)
    foto = models.ImageField(upload_to='perfiles/', blank=True, null=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.get_rol_display()}"


# =====================================================
# 2. CUPONES DE DESCUENTO (NUEVO)
# =====================================================
class Cupon(models.Model):
    TIPO_CUPON = (
        ('CANCHA', 'Alquiler de Cancha'),
        ('TORNEO', 'Inscripción de Campeonato'),
    )
    codigo = models.CharField(max_length=20, unique=True, help_text="Ej: GOLAZO2026")
    descuento = models.DecimalField(max_digits=5, decimal_places=2, help_text="Monto en $ a descontar")
    tipo = models.CharField(max_length=15, choices=TIPO_CUPON)
    activo = models.BooleanField(default=True)
    
    # Control de uso
    usos_actuales = models.PositiveIntegerField(default=0)
    limite_usos = models.PositiveIntegerField(null=True, blank=True, help_text="Dejar vacío para ilimitado")
    fecha_expiracion = models.DateField(null=True, blank=True)

    def es_valido(self):
        ahora = timezone.now().date()
        if not self.activo: return False
        if self.fecha_expiracion and ahora > self.fecha_expiracion: return False
        if self.limite_usos and self.usos_actuales >= self.limite_usos: return False
        return True

    def __str__(self):
        return f"CUPÓN: {self.codigo} (-${self.descuento})"


# =====================================================
# 3. TORNEOS
# =====================================================
class Torneo(models.Model):
    nombre = models.CharField(max_length=100)
    organizador = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_inicio = models.DateField(default=timezone.now)
    activo = models.BooleanField(default=True)
    costo_inscripcion = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    costo_amarilla = models.DecimalField(max_digits=5, decimal_places=2, default=2.00, verbose_name="Multa Amarilla ($)")
    costo_roja = models.DecimalField(max_digits=5, decimal_places=2, default=5.00, verbose_name="Multa Roja ($)")
    
    inscripcion_abierta = models.BooleanField(default=True, verbose_name="¿Inscripción Habilitada?")
    fecha_limite_inscripcion = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.nombre

    @property
    def periodo_valido(self):
        if self.fecha_limite_inscripcion:
            return date.today() <= self.fecha_limite_inscripcion
        return True


# =====================================================
# 4. EQUIPOS (Con Estado de Aprobación)
# =====================================================
class Equipo(models.Model):
    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE, related_name='equipos')
    dirigente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='equipo_dirigido')
    nombre = models.CharField(max_length=100)
    escudo = models.ImageField(upload_to='escudos/', null=True, blank=True)
    nombre_suplente_1 = models.CharField(max_length=100, blank=True)
    nombre_suplente_2 = models.CharField(max_length=100, blank=True)
    pagado = models.BooleanField(default=False, verbose_name="Inscripción Pagada")
    monto_reembolso = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Bonificación y Grupos
    puntos_bonificacion = models.IntegerField(default=0)
    GRUPO_FASE2_CHOICES = [('A', 'Grupo A'), ('B', 'Grupo B'), ('N', 'Ninguno')]
    grupo_fase2 = models.CharField(max_length=1, choices=GRUPO_FASE2_CHOICES, default='N')

    # --- NUEVO: ESTADO DE INSCRIPCIÓN ---
    ESTADOS_INSCRIPCION = [
        ('PENDIENTE', '⏳ Pendiente de Aprobación'),
        ('APROBADO', '✅ Aprobado'),
        ('RECHAZADO', '❌ Rechazado'),
    ]
    estado_inscripcion = models.CharField(max_length=10, choices=ESTADOS_INSCRIPCION, default='PENDIENTE')

    def __str__(self):
        return self.nombre
    
    # Métodos Financieros
    def total_pagado(self):
        resultado = self.pagos.aggregate(total=Sum('monto'))['total']
        return resultado or 0

    def total_multas(self):
        resultado = self.multas_recibidas.aggregate(total=Sum('monto'))['total']
        return resultado or 0

    def deuda_pendiente(self):
        valor_inscripcion = self.torneo.costo_inscripcion
        multas = self.total_multas()
        pagado = self.total_pagado()
        return (valor_inscripcion + multas) - pagado
    
    def tiene_deudas(self):
        """ Retorna True si tiene sanciones sin pagar """
        return self.sanciones.filter(pagada=False).exists()

    def total_deuda(self):
        """ Retorna el monto total adeudado """
        from django.db.models import Sum
        total = self.sanciones.filter(pagada=False).aggregate(Sum('monto'))['monto__sum']
        return total or 0.00


# =====================================================
# 5. PAGOS (Abonos de Torneo)
# =====================================================
class Pago(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=date.today)
    comprobante = models.ImageField(upload_to='pagos/', null=True, blank=True)
    validado = models.BooleanField(default=False)
    observacion = models.TextField(max_length=500, blank=True, null=True)
    
    def __str__(self):
        return f"Abono ${self.monto} - {self.equipo.nombre}"


# =====================================================
# 6. JUGADORES
# =====================================================
class Jugador(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='jugadores')
    nombres = models.CharField(max_length=100)
    dorsal = models.PositiveIntegerField()
    cedula = models.CharField(max_length=15, unique=True)
    foto = models.ImageField(upload_to='jugadores/', null=True, blank=True)
    
    rojas_directas_acumuladas = models.PositiveIntegerField(default=0)
    expulsado_torneo = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nombres} ({self.dorsal})"


# =====================================================
# 7. PARTIDOS
# =====================================================
class Partido(models.Model):
    ESTADOS = [('PROG', 'Programado'), ('JUG', 'Finalizado'), ('WO', 'Walkover')]
    ETAPAS = [
        ('F1', 'Fase 1'), ('F2', 'Fase 2'), 
        ('4TOS', 'Cuartos'), ('SEMI', 'Semifinal'), ('FINAL', 'Final')
    ]
    
    # Informes
    informe_vocal = models.TextField(blank=True, null=True)
    informe_arbitro = models.TextField(blank=True, null=True)
    validado_local = models.BooleanField(default=False)
    validado_visita = models.BooleanField(default=False)

    numero_fecha = models.PositiveIntegerField(default=1)
    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE)
    etapa = models.CharField(max_length=5, choices=ETAPAS, default='F1')
    cancha = models.CharField(max_length=100, default="Cancha Principal")
    
    equipo_local = models.ForeignKey(Equipo, related_name='local', on_delete=models.CASCADE)
    equipo_visita = models.ForeignKey(Equipo, related_name='visita', on_delete=models.CASCADE)
    fecha_hora = models.DateTimeField()
    
    goles_local = models.PositiveIntegerField(default=0)
    goles_visita = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=4, choices=ESTADOS, default='PROG')
    ganador_wo = models.ForeignKey(Equipo, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.equipo_local} vs {self.equipo_visita}"


# =====================================================
# 8. DETALLE Y MULTAS DEL PARTIDO
# =====================================================
class DetallePartido(models.Model):
    TIPOS = [
        ('GOL', '⚽ Gol'), ('ASIS', '✅ Asistencia'), ('TA', '🟨 Amarilla'),
        ('TR', '🟥 Roja'), ('DA', '🟨🟨 Doble A.'), ('AZUL', '👕 Uniforme'), ('EBRI', '🍺 Ebrio')
    ]
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE, related_name='detalles')
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=5, choices=TIPOS)
    minuto = models.PositiveIntegerField(blank=True, null=True, default=0) 
    observacion = models.TextField(blank=True, null=True)

class Multa(models.Model):
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE, related_name='multas')
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='multas_recibidas')
    motivo = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    pagado = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)


# =====================================================
# 9. RESERVA DE CANCHA (NUEVO - Lógica Amazon/Cancha)
# =====================================================
class ReservaCancha(models.Model):
    # Usuario es null si el Organizador bloquea para el torneo
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservas', null=True, blank=True)
    
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    
    # Estados
    precio_total = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    pagado = models.BooleanField(default=False)
    
    # Bloqueo Organizador
    es_torneo = models.BooleanField(default=False, verbose_name="Bloqueo por Torneo")
    motivo_bloqueo = models.CharField(max_length=100, blank=True, null=True)
    
    cupon = models.ForeignKey(Cupon, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    partido = models.OneToOneField('Partido', on_delete=models.CASCADE, null=True, blank=True, related_name='reserva_bloqueo')

    ESTADOS = [
        ('PENDIENTE', '⏳ Pendiente'), # <-- NUEVO ESTADO AGREGADO
        ('ACTIVA', '✅ Confirmada'),
        ('CANCELADA', '🚫 Cancelada'),
    ]
    # OJO: Cambia el max_length a 15 y pon el default en 'PENDIENTE'
    estado = models.CharField(max_length=15, choices=ESTADOS, default='PENDIENTE')

    def clean(self):
        """ REGLAS DE NEGOCIO """
        # 1. NUEVO HORARIO: 3PM a 9PM (15:00 a 21:00)
        APERTURA = time(15, 0)
        CIERRE = time(21, 0)

        if self.hora_inicio < APERTURA or self.hora_fin > CIERRE:
            raise ValidationError("⚠️ La cancha opera de 03:00 PM a 09:00 PM.")
        
        if self.hora_inicio >= self.hora_fin:
            raise ValidationError("⚠️ Hora inicio debe ser menor a hora fin.")
        
        if self.hora_inicio.minute != 0 or self.hora_fin.minute != 0:
             raise ValidationError("⚠️ Solo se permiten reservas en horas exactas (ej: 15:00, 16:00).")

        # 2. ANTICIPACIÓN DE 1 DÍA (Solo para clientes, no bloquea al Organizador)
        if not self.es_torneo:
            from django.utils import timezone
            if self.fecha <= timezone.now().date():
                raise ValidationError("⚠️ Solo se aceptan reservas con al menos 1 día de anticipación.")

        # 3. Evitar Choques de Horario
        choque = ReservaCancha.objects.filter(
            fecha=self.fecha,
            hora_inicio__lt=self.hora_fin,
            hora_fin__gt=self.hora_inicio
        ).exclude(id=self.id).exclude(estado='CANCELADA') # IMPORTANTE: Ignoramos las canceladas

        if choque.exists():
            c = choque.first()
            msg = "⛔ Reservado para CAMPEONATO" if c.es_torneo else "⛔ Ya reservado por otro cliente"
            raise ValidationError(msg)

    def save(self, *args, **kwargs):
        """ CÁLCULO DE PRECIO AUTOMÁTICO Y BLINDAJE DE DATOS """
        from decimal import Decimal
        
        # 🔥 ESCUDO ANTI-ERRORES (Soluciona el IntegrityError)
        if self.monto_reembolso is None:
            self.monto_reembolso = Decimal('0.00')
        if self.precio_total is None:
            self.precio_total = Decimal('0.00')
            
        if not self.es_torneo:
            formato = "%H:%M:%S"
            ini = datetime.strptime(str(self.hora_inicio), formato)
            fin = datetime.strptime(str(self.hora_fin), formato)
            horas = (fin - ini).seconds / 3600
            
            # PRECIO FIJO A $5 LA HORA
            base = float(horas) * 5.00
            
            # Aplicar Cupón
            if self.cupon and self.cupon.es_valido():
                total = max(0, base - float(self.cupon.descuento))
                if not self.pk: # Contar uso solo al crear
                    self.cupon.usos_actuales += 1
                    self.cupon.save()
            else:
                total = base
            
            self.precio_total = Decimal(str(total))
        else:
            self.precio_total = Decimal('0.00')
            
        super().save(*args, **kwargs)

    def __str__(self):
        tipo = "TORNEO" if self.es_torneo else "CLIENTE"
        return f"{self.fecha} | {self.hora_inicio}-{self.hora_fin} ({tipo})"

class Sancion(models.Model):
    TIPOS = [('AMARILLA', 'Tarjeta Amarilla'), ('ROJA', 'Tarjeta Roja'), ('ADMIN', 'Sanción Administrativa')]
    
    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE)
    equipo = models.ForeignKey('Equipo', on_delete=models.CASCADE, related_name='sanciones')
    
    jugador = models.ForeignKey('Jugador', on_delete=models.SET_NULL, null=True, blank=True)
    partido = models.ForeignKey('Partido', on_delete=models.SET_NULL, null=True, blank=True)
    
    tipo = models.CharField(max_length=10, choices=TIPOS)
    monto = models.DecimalField(max_digits=5, decimal_places=2)
    descripcion = models.CharField(max_length=200, blank=True)
    
    pagada = models.BooleanField(default=False, verbose_name="¿Multa Pagada?")
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        estado = "PAGADO" if self.pagada else "DEUDA"
        return f"{self.equipo.nombre} - {self.tipo} (${self.monto}) [{estado}]"
    
# --- core/models.py ---

class Configuracion(models.Model):
    """ Para guardar valores globales como el IVA """
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)
    precio_hora_cancha = models.DecimalField(max_digits=6, decimal_places=2, default=15.00) # Precio BASE sin IVA

    def __str__(self):
        return f"Configuración del Sistema (IVA: {self.iva_porcentaje}%)"

    class Meta:
        verbose_name = "Configuración"
        verbose_name_plural = "Configuraciones"