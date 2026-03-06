from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Count, Q, Sum
from django.template.loader import get_template
from django.db import transaction 
from xhtml2pdf import pisa 
from django.db import models
from django.contrib.auth.models import User
from .forms import ReservaCanchaForm
from .models import ReservaCancha, Cupon
from django.utils import timezone  
from datetime import datetime, time, timedelta
from django.core.exceptions import ValidationError
from .models import Configuracion, Sancion, DetallePartido
from urllib.parse import quote

# Importamos Modelos y Formularios
from .models import Torneo, Equipo, Jugador, Partido, DetallePartido, Pago, Multa, Perfil, Sancion
from .forms import (
    RegistroUsuarioForm, TorneoForm, EquipoForm, JugadorForm, 
    ProgramarPartidoForm, PagoForm, RegistroPublicoForm
)
from .utils import validar_cedula_ecuador, consultar_sri

# =========================================================
# --- FUNCIONES DE CONTROL DE ACCESO (PERMISOS) ---
# =========================================================

def es_organizador(user):
    # Solo deja pasar si es el JEFE (ORG)
    return user.is_authenticated and hasattr(user, 'perfil') and user.perfil.rol == 'ORG'

def es_vocal_o_admin(user):
    # Deja pasar al JEFE (ORG) y al VOCAL (VOC)
    return user.is_authenticated and hasattr(user, 'perfil') and user.perfil.rol in ['ORG', 'VOC']

def es_dirigente_o_admin(user):
    # Deja pasar al JEFE (ORG) y al DIRIGENTE (DIR)
    return user.is_authenticated and hasattr(user, 'perfil') and user.perfil.rol in ['ORG', 'DIR']

# =========================================================
# 1. VISTAS GENERALES Y DE GESTIÓN (CRUD)
# =========================================================

def dashboard(request):
    """ 
    Portada inteligente: 
    - Si es ORG: Ve cuentas por cobrar y reservas pendientes.
    - Si es DIR: Ve si tiene multas pendientes.
    - Si es Invitado: Ve opciones generales.
    """
    ctx = {}

    # Solo procesamos lógica extra si el usuario está logueado
    if request.user.is_authenticated and hasattr(request.user, 'perfil'):
        rol = request.user.perfil.rol

        # ---------------------------------------------------------
        # 1. LOGICA PARA EL ORGANIZADOR (Panel de Cobros y Reservas)
        # ---------------------------------------------------------
        if rol == 'ORG':
            # A) Buscamos TODAS las sanciones sin pagar
            deudas_pendientes = Sancion.objects.filter(pagada=False).select_related('equipo', 'torneo').order_by('-fecha_creacion')
            total = deudas_pendientes.aggregate(Sum('monto'))['monto__sum'] or 0
            
            # B) 🔥 NUEVO: Buscamos las reservas pendientes de aprobación
            reservas_pendientes = ReservaCancha.objects.filter(estado='PENDIENTE').select_related('usuario').order_by('fecha', 'hora_inicio')
            
            ctx['deudas'] = deudas_pendientes
            ctx['total_por_cobrar'] = total
            ctx['reservas_pendientes'] = reservas_pendientes # <--- Enviamos esto al HTML

        # ---------------------------------------------------------
        # 2. LOGICA PARA EL DIRIGENTE (Alerta de Deuda Personal)
        # ---------------------------------------------------------
        elif rol == 'DIR':
            # ... (tu código del dirigente se queda igual, no lo toques)
            try:
                mi_equipo = Equipo.objects.get(dirigente=request.user)
                ctx['mi_equipo'] = mi_equipo
                
                mis_deudas = Sancion.objects.filter(equipo=mi_equipo, pagada=False)
                if mis_deudas.exists():
                    total_deuda = mis_deudas.aggregate(Sum('monto'))['monto__sum'] or 0
                    ctx['tengo_deudas'] = True
                    ctx['monto_deuda'] = total_deuda
                    ctx['lista_mis_deudas'] = mis_deudas
            
            except Equipo.DoesNotExist:
                ctx['mi_equipo'] = None

    return render(request, 'core/dashboard.html', ctx)

@login_required
@user_passes_test(es_organizador)
def crear_usuario(request):
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            u = form.save()
            u.perfil.rol = form.cleaned_data['rol']
            u.perfil.save()
            messages.success(request, f'Usuario "{u.username}" creado.')
            return redirect('dashboard')
    else:
        form = RegistroUsuarioForm()
    return render(request, 'core/crear_usuario.html', {'form': form})

# --- GESTIÓN DE USUARIOS (NUEVO) ---
@login_required
@user_passes_test(es_organizador)
def gestionar_usuarios(request):
    # Traemos todos menos al usuario actual
    perfiles = Perfil.objects.all().exclude(usuario=request.user).select_related('usuario').order_by('-id')
    
    if request.method == 'POST':
        perfil_id = request.POST.get('perfil_id')
        nuevo_rol = request.POST.get('nuevo_rol')
        
        if perfil_id and nuevo_rol:
            p = Perfil.objects.get(id=perfil_id)
            p.rol = nuevo_rol
            p.save()
            messages.success(request, f'Rol de {p.usuario.username} actualizado a {p.get_rol_display()}')
            return redirect('gestionar_usuarios')

    return render(request, 'core/gestionar_usuarios.html', {'perfiles': perfiles})

@login_required
@user_passes_test(es_organizador)
def gestionar_torneos(request):
    mis_torneos = Torneo.objects.filter(organizador=request.user)
    if request.method == 'POST':
        form = TorneoForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.organizador = request.user
            t.save()
            messages.success(request, f'Torneo "{t.nombre}" creado.')
            return redirect('gestionar_torneos')
    else:
        form = TorneoForm()
    return render(request, 'core/gestionar_torneos.html', {'form': form, 'torneos': mis_torneos})

# --- EQUIPOS ---

@login_required
@user_passes_test(es_organizador)
def gestionar_equipos(request):
    equipos = Equipo.objects.all().select_related('torneo', 'dirigente')
    if request.method == 'POST':
        form = EquipoForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Equipo inscrito correctamente!')
            return redirect('gestionar_equipos')
    else:
        form = EquipoForm()
    return render(request, 'core/gestionar_equipos.html', {'form': form, 'equipos': equipos})

@login_required
@user_passes_test(es_organizador)
def editar_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    if request.method == 'POST':
        form = EquipoForm(request.POST, request.FILES, instance=equipo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipo actualizado correctamente.')
            return redirect('gestionar_equipos')
    else:
        form = EquipoForm(instance=equipo)
    return render(request, 'core/gestionar_equipos.html', {'form': form, 'equipos': Equipo.objects.all(), 'editando': True})

@login_required
@user_passes_test(es_organizador)
def eliminar_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    equipo.delete()
    messages.success(request, 'Equipo eliminado.')
    return redirect('gestionar_equipos')

# --- JUGADORES (CON LÓGICA INTELIGENTE PARA DIRIGENTES) ---

@login_required
def gestionar_jugadores(request):
    perfil = request.user.perfil
    
    # === REGLA 1: SI ES DIRIGENTE, SOLO VE SU PROPIO EQUIPO ===
    if perfil.rol == 'DIR':
        # Buscamos SU equipo. Si no tiene, no puede ver nada.
        try:
            mi_equipo = Equipo.objects.get(dirigente=request.user)
        except Equipo.DoesNotExist:
            messages.error(request, 'No tienes un equipo inscrito. Inscríbete a un torneo primero.')
            return redirect('ver_torneos_activos')

        # Forzamos que la consulta sea SOLO de su equipo
        jugadores = Jugador.objects.filter(equipo=mi_equipo).order_by('dorsal')
        equipos = [mi_equipo] # En el select solo aparecerá su equipo
        equipo_seleccionado = mi_equipo.id
        
        # Procesar Formulario (Fichar Jugador)
        if request.method == 'POST':
            form = JugadorForm(request.POST, request.FILES)
            if form.is_valid():
                jugador = form.save(commit=False)
                jugador.equipo = mi_equipo 
                jugador.save()
                
                # --- CORRECCIÓN AQUÍ: Se usa .nombres (plural) ---
                messages.success(request, f'¡{jugador.nombres} fichado en {mi_equipo.nombre}!')
                return redirect('gestionar_jugadores')
    
    # === REGLA 2: SI ES ORGANIZADOR, VE TODO ===
    elif perfil.rol == 'ORG':
        equipos = Equipo.objects.all()
        equipo_id = request.GET.get('equipo')
        
        if equipo_id:
            jugadores = Jugador.objects.filter(equipo_id=equipo_id).order_by('dorsal')
            equipo_seleccionado = int(equipo_id)
        else:
            jugadores = Jugador.objects.none() # Que seleccione uno primero
            equipo_seleccionado = None
            
        if request.method == 'POST':
            form = JugadorForm(request.POST, request.FILES)
            if form.is_valid():
                nuevo_jugador = form.save()
                # --- CORRECCIÓN AQUÍ: Se usa .nombres ---
                messages.success(request, f'Jugador {nuevo_jugador.nombres} registrado por Administración.')
                return redirect(f"{request.path}?equipo={form.cleaned_data['equipo'].id}")

    # === REGLA 3: CUALQUIER OTRO (Vocal/Fan) FUERA ===
    else:
        messages.error(request, "Acceso denegado.")
        return redirect('dashboard')


    if perfil.rol == 'DIR':
        form = JugadorForm(initial={'equipo': mi_equipo}) 
    else:
        form = JugadorForm()

    return render(request, 'core/gestionar_jugadores.html', {
        'form': form, 
        'jugadores': jugadores, 
        'equipos': equipos,
        'equipo_seleccionado': equipo_seleccionado,
        'es_dirigente': (perfil.rol == 'DIR')
    })

@login_required
@user_passes_test(es_organizador)
def editar_jugador(request, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id)
    if request.method == 'POST':
        form = JugadorForm(request.POST, request.FILES, instance=jugador)
        if form.is_valid():
            form.save()
            messages.success(request, 'Jugador actualizado.')
            return redirect(f"/jugadores/?equipo={jugador.equipo.id}")
    else:
        form = JugadorForm(instance=jugador)
    
    return render(request, 'core/gestionar_jugadores.html', {
        'form': form, 
        'jugadores': Jugador.objects.filter(equipo=jugador.equipo), 
        'equipos': Equipo.objects.all(),
        'editando': True
    })

@login_required
def eliminar_jugador(request, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id)
    es_admin = request.user.perfil.rol == 'ORG'
    es_dueno = (request.user.perfil.rol == 'DIR' and jugador.equipo.dirigente == request.user)

    # 1. VALIDACIÓN DE SEGURIDAD
    if not (es_admin or es_dueno):
        messages.error(request, "No tienes permiso para eliminar a este jugador.")
        return redirect('dashboard')

    # 2. VALIDACIÓN DE INTEGRIDAD 
    # Evitar borrar jugadores que ya jugaron y tienen goles/tarjetas
    # Si borras un jugador con goles, se borran sus goles del historial
    if jugador.detallepartido_set.exists():
        messages.error(request, f"No se puede eliminar a {jugador.nombres} porque ya tiene registros (goles/tarjetas) en partidos jugados.")
        # Redirigimos según quién sea
        if es_admin: return redirect('admin_gestion_jugadores')
        else: return redirect('gestionar_jugadores')

    # 3. PROCEDER A ELIMINAR
    equipo_id = jugador.equipo.id
    nombre = jugador.nombres
    jugador.delete()
    
    messages.success(request, f'Jugador "{nombre}" eliminado correctamente.')
    
    # Retorno inteligente
    if es_admin:
        return redirect('admin_gestion_jugadores')
    else:
        return redirect('gestionar_jugadores')

# --- API SRI/REGISTRO CIVIL ---

def api_consultar_cedula(request):
    cedula = request.GET.get('cedula', '')
    if not validar_cedula_ecuador(cedula):
        return JsonResponse({'error': 'Cédula inválida o incorrecta.'}, status=400)
    
    nombre = consultar_sri(cedula)
    if nombre:
        return JsonResponse({'nombre': nombre, 'exito': True})
    else:
        return JsonResponse({'exito': False, 'mensaje': 'Cédula válida, sin datos públicos.'})


# =========================================================
# 2. CALENDARIO Y PARTIDOS (ACCESO VOCAL Y ADMIN)
# =========================================================

@login_required
@user_passes_test(es_vocal_o_admin)
def programar_partidos(request):
    torneos = Torneo.objects.all()
    torneo_seleccionado = request.GET.get('torneo')
    
    # Si hay torneo seleccionado, mostramos sus partidos. Si no, lista vacía.
    partidos = Partido.objects.filter(torneo_id=torneo_seleccionado).order_by('-fecha_hora') if torneo_seleccionado else []
    
    if request.method == 'POST' and es_organizador(request.user):
        form = ProgramarPartidoForm(request.POST)
        
        if form.is_valid():
            # --- 1. REGLA DE ORO: VALIDACIÓN DE DEUDAS ---
            # Antes de guardar nada, revisamos la billetera de los equipos.
            equipo_local = form.cleaned_data['equipo_local']
            equipo_visita = form.cleaned_data['equipo_visita']
            
            errores_deuda = []
            
            if equipo_local.tiene_deudas():
                errores_deuda.append(f"🚫 PROHIBIDO: {equipo_local.nombre} tiene una deuda de ${equipo_local.total_deuda()}. No puede jugar.")
            
            if equipo_visita.tiene_deudas():
                errores_deuda.append(f"🚫 PROHIBIDO: {equipo_visita.nombre} tiene una deuda de ${equipo_visita.total_deuda()}. No puede jugar.")
                
            if errores_deuda:
                # Si hay deudas, mostramos los errores y cancelamos todo.
                for error in errores_deuda:
                    messages.error(request, error)
                # Recargamos la página manteniendo el torneo seleccionado
                return redirect(f"{request.path}?torneo={form.cleaned_data['torneo'].id}")

            # --- 2. SI NO HAY DEUDAS, PROCEDEMOS ---
            try:
                # A) Guardamos el Partido en la BD
                partido = form.save()
                
                # B) CREAR BLOQUEO AUTOMÁTICO EN LA CANCHA
                # Asumimos que un partido dura 2 horas
                duracion = 2 
                hora_fin_estimada = (partido.fecha_hora + timedelta(hours=duracion)).time()
                
                # Creamos la reserva vinculada (Esto bloquea la cancha para clientes)
                ReservaCancha.objects.create(
                    fecha=partido.fecha_hora.date(),
                    hora_inicio=partido.fecha_hora.time(),
                    hora_fin=hora_fin_estimada,
                    es_torneo=True, # Marca especial para que salga naranja/amarillo
                    motivo_bloqueo=f"⚽ {partido.equipo_local} vs {partido.equipo_visita}",
                    partido=partido, # Vínculo para que si borras el partido, se borre la reserva
                    usuario=request.user # El organizador es el dueño de la reserva
                )

                messages.success(request, '✅ Partido agendado y cancha bloqueada automáticamente.')
                return redirect(f"{request.path}?torneo={form.cleaned_data['torneo'].id}")
            
            except ValidationError as e:
                # Si la cancha ya estaba ocupada por un cliente, la ReservaCancha lanzará error
                partido.delete() # IMPORTANTE: Borramos el partido para no dejar datos "huerfanos"
                messages.error(request, f'⛔ No se pudo programar: La cancha ya está reservada en ese horario por un cliente.')
            
            except Exception as e:
                # Captura cualquier otro error raro
                if 'partido' in locals() and partido.id: 
                    partido.delete()
                messages.error(request, f'Error de conflicto: {str(e)}')
                
    else:
        # Pre-seleccionar el torneo en el formulario si ya lo elegimos en el filtro
        form = ProgramarPartidoForm(initial={'torneo': torneo_seleccionado})

    return render(request, 'core/programar_partidos.html', {
        'partidos': partidos, 
        'form': form, 
        'torneos': torneos,
        'torneo_actual': int(torneo_seleccionado) if torneo_seleccionado else None
    })

@login_required
@user_passes_test(es_organizador)
def editar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    
    if request.method == 'POST':
        form = ProgramarPartidoForm(request.POST, instance=partido)
        if form.is_valid():
            form.save()
            messages.success(request, 'Datos del partido actualizados.')
            return redirect(f"/programar/?torneo={partido.torneo.id}")
    else:
        form = ProgramarPartidoForm(instance=partido)

    return render(request, 'core/editar_partido.html', {'form': form, 'partido': partido})

@login_required
@user_passes_test(es_organizador)
def eliminar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    torneo_id = partido.torneo.id
    partido.delete()
    messages.warning(request, 'Partido eliminado del calendario.')
    return redirect(f"/programar/?torneo={torneo_id}")

@login_required
@user_passes_test(es_organizador)
def reiniciar_partido(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    partido.detalles.all().delete()
    partido.multas.all().delete() 
    partido.goles_local = 0
    partido.goles_visita = 0
    partido.estado = 'PROG'
    partido.informe_vocal = ""
    partido.informe_arbitro = ""
    partido.validado_local = False
    partido.validado_visita = False
    partido.save()
    messages.info(request, 'El partido ha sido reiniciado. Ahora está pendiente de juego.')
    return redirect(f"/programar/?torneo={partido.torneo.id}")


# =========================================================
# 3. JUEGO, VOCALÍA Y RESULTADOS (ACCESO VOCAL Y ADMIN)
# =========================================================

@login_required
@user_passes_test(es_vocal_o_admin) # <--- PERMISO EXPANDIDO
def registrar_resultado(request, partido_id):
    partido = Partido.objects.get(id=partido_id)
    
    if request.method == 'POST':
        goles_local = request.POST.get('goles_local')
        goles_visita = request.POST.get('goles_visita')
        wo = request.POST.get('wo')

        if wo == 'on':
            partido.estado = 'WO'
            partido.goles_local = 3
            partido.goles_visita = 0
        else:
            partido.goles_local = int(goles_local)
            partido.goles_visita = int(goles_visita)
            partido.estado = 'JUG'

        partido.save()
        messages.success(request, f'Resultado registrado: {partido.equipo_local} ({partido.goles_local}) - ({partido.goles_visita}) {partido.equipo_visita}')
        return redirect(f"/programar/?torneo={partido.torneo.id}")

    return render(request, 'core/registrar_resultado.html', {'partido': partido})


@login_required
@user_passes_test(es_vocal_o_admin)
def gestionar_vocalia(request, partido_id):
    partido = get_object_or_404(Partido, id=partido_id)
    
    # --- 1. DATOS PARA LA VISTA ---
    jugadores_local = Jugador.objects.filter(equipo=partido.equipo_local).order_by('dorsal')
    jugadores_visita = Jugador.objects.filter(equipo=partido.equipo_visita).order_by('dorsal')
    eventos = DetallePartido.objects.filter(partido=partido).order_by('-id')
    asistencias_ids = list(DetallePartido.objects.filter(partido=partido, tipo='ASIS').values_list('jugador_id', flat=True))
    
    # Mostramos las Sanciones reales vinculadas al partido
    multas = Sancion.objects.filter(partido=partido).order_by('-id')

    if request.method == 'POST':
        
        # CASO A: GUARDAR INFORMES Y VALIDACIONES
        if 'guardar_informe' in request.POST:
            partido.informe_vocal = request.POST.get('informe_vocal')
            partido.informe_arbitro = request.POST.get('informe_arbitro')
            partido.validado_local = request.POST.get('validado_local') == 'on'
            partido.validado_visita = request.POST.get('validado_visita') == 'on'
            partido.save()
            messages.success(request, '📝 Informes actualizados.')
            return redirect('gestionar_vocalia', partido_id=partido_id)
        
        # CASO B: NUEVA MULTA MANUAL (BARRA, GRADERIO, ETC) - PRECIO DIRECTO
        elif 'nueva_multa' in request.POST:
            equipo_id_multa = request.POST.get('equipo_multa')
            motivo_multa = request.POST.get('motivo_multa')
            monto_str = request.POST.get('monto_multa')
            
            if equipo_id_multa and motivo_multa and monto_str:
                equipo_obj = Equipo.objects.get(id=equipo_id_multa)
                monto_real = float(monto_str)
                
                Sancion.objects.create(
                    torneo=partido.torneo,
                    equipo=equipo_obj,
                    partido=partido,
                    tipo='ADMIN',
                    monto=monto_real, # Valor tal cual se ingresa en el formulario
                    descripcion=motivo_multa,
                    pagada=False
                )
                messages.warning(request, f'💸 Multa aplicada: ${monto_real} a {equipo_obj.nombre}')
            return redirect('gestionar_vocalia', partido_id=partido_id)

        # CASO C: EVENTOS DEL JUEGO (GOLES, TARJETAS)
        jugador_id = request.POST.get('jugador_id')
        tipo_evento = request.POST.get('tipo')
        obs = request.POST.get('observacion', '')

        if jugador_id and tipo_evento:
            jugador = Jugador.objects.get(id=jugador_id)
            
            # Evitar doble asistencia
            if tipo_evento == 'ASIS' and jugador.id in asistencias_ids:
                messages.warning(request, f'{jugador.nombres} ya tiene asistencia.')
                return redirect('gestionar_vocalia', partido_id=partido_id)

            # 1. Crear Evento Estadístico
            DetallePartido.objects.create(
                partido=partido,
                jugador=jugador,
                tipo=tipo_evento,
                observacion=obs
            )
            
            # 2. Lógica de Goles
            if tipo_evento == 'GOL':
                if jugador.equipo == partido.equipo_local:
                    partido.goles_local += 1
                else:
                    partido.goles_visita += 1
                partido.estado = 'JUG'
                partido.save()
                messages.success(request, f'⚽ ¡Gol de {jugador.nombres}!')
            
            # 3. Lógica de Tarjetas (PRECIO DIRECTO DEL TORNEO)
            elif tipo_evento in ['TA', 'TR']:
                monto_sancion = 0.0
                tipo_sancion = ''
                
                if tipo_evento == 'TA':
                    monto_sancion = float(partido.torneo.costo_amarilla)
                    tipo_sancion = 'AMARILLA'
                elif tipo_evento == 'TR':
                    monto_sancion = float(partido.torneo.costo_roja)
                    tipo_sancion = 'ROJA'
                
                if monto_sancion > 0:
                    Sancion.objects.create(
                        torneo=partido.torneo,
                        equipo=jugador.equipo,
                        jugador=jugador,
                        partido=partido,
                        tipo=tipo_sancion,
                        monto=monto_sancion, # Sin impuestos, valor neto
                        pagada=False,
                        descripcion=f"Sanción en partido vs {partido.equipo_visita.nombre if jugador.equipo == partido.equipo_local else partido.equipo_local.nombre}"
                    )
                    messages.warning(request, f'⚖️ Tarjeta registrada. Multa de ${monto_sancion} generada.')

            elif tipo_evento == 'ASIS':
                messages.info(request, f'✅ Asistencia registrada para {jugador.nombres}')

            return redirect('gestionar_vocalia', partido_id=partido_id)

    return render(request, 'core/gestionar_vocalia.html', {
        'partido': partido,
        'jugadores_local': jugadores_local,
        'jugadores_visita': jugadores_visita,
        'eventos': eventos,
        'asistencias_ids': asistencias_ids,
        'multas': multas
    })


@login_required
@user_passes_test(es_vocal_o_admin) # <--- PERMISO EXPANDIDO
def eliminar_evento(request, evento_id):
    evento = DetallePartido.objects.get(id=evento_id)
    partido = evento.partido
    
    if evento.tipo == 'GOL':
        if evento.jugador.equipo == partido.equipo_local:
            partido.goles_local = max(0, partido.goles_local - 1)
        else:
            partido.goles_visita = max(0, partido.goles_visita - 1)
        partido.save()
    
    evento.delete()
    messages.success(request, 'Corrección realizada: Evento eliminado.')
    return redirect('gestionar_vocalia', partido_id=partido.id)

@login_required
@user_passes_test(es_vocal_o_admin) # <--- PERMISO EXPANDIDO
def eliminar_multa(request, multa_id):
    multa = get_object_or_404(Multa, id=multa_id)
    partido_id = multa.partido.id
    multa.delete()
    messages.success(request, 'Multa eliminada correctamente.')
    return redirect('gestionar_vocalia', partido_id=partido_id)

@login_required
@user_passes_test(es_vocal_o_admin) # <--- PERMISO EXPANDIDO
def toggle_asistencia(request, partido_id, jugador_id):
    partido = Partido.objects.get(id=partido_id)
    jugador = Jugador.objects.get(id=jugador_id)
    
    asistencia = DetallePartido.objects.filter(partido=partido, jugador=jugador, tipo='ASIS').first()
    
    if asistencia:
        asistencia.delete()
        messages.warning(request, f'Se quitó la asistencia a {jugador.nombres}')
    else:
        DetallePartido.objects.create(partido=partido, jugador=jugador, tipo='ASIS')
        messages.success(request, f'✅ Asistencia marcada: {jugador.nombres}')
        
    return redirect('gestionar_vocalia', partido_id=partido_id)


# =========================================================
# 4. REPORTES Y ESTADÍSTICAS
# =========================================================

# --- TABLA FASE 1 (La normal) ---
@login_required
def tabla_posiciones(request, torneo_id):
    torneo = Torneo.objects.get(id=torneo_id)
    equipos = Equipo.objects.filter(torneo=torneo)
    tabla = []

    for equipo in equipos:
        # FILTRO: Solo contamos partidos de la FASE 1 ('F1')
        partidos = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visita=equipo),
            estado__in=['JUG', 'WO'],
            etapa='F1' 
        )
        
        pj = 0; pg = 0; pe = 0; pp = 0; gf = 0; gc = 0
        
        for p in partidos:
            pj += 1
            es_local = (p.equipo_local == equipo)
            goles_propios = p.goles_local if es_local else p.goles_visita
            goles_rival = p.goles_visita if es_local else p.goles_local
            
            gf += goles_propios
            gc += goles_rival
            
            if goles_propios > goles_rival: pg += 1
            elif goles_propios < goles_rival: pp += 1
            else: pe += 1
        
        # En Fase 1 NO sumamos bonificación aún
        puntos = (pg * 3) + (pe * 1)
        gol_diferencia = gf - gc
        
        tabla.append({
            'equipo': equipo,
            'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp,
            'gf': gf, 'gc': gc, 'gd': gol_diferencia,
            'pts': puntos,
            'bono': 0
        })
    
    tabla_ordenada = sorted(tabla, key=lambda x: (x['pts'], x['gd']), reverse=True)

    # Enviamos 'fase': 1 para controlar el botón en el HTML
    return render(request, 'core/tabla_posiciones.html', {
        'torneo': torneo, 
        'tabla': tabla_ordenada, 
        'fase': 1
    })


# --- LÓGICA DE TRANSICIÓN (Botón Mágico) ---
@login_required
@user_passes_test(es_organizador)
def generar_fase_2(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    # 1. Calculamos la tabla F1 internamente para saber quién quedó 1ro y 2do
    equipos = Equipo.objects.filter(torneo=torneo)
    tabla = []

    for equipo in equipos:
        partidos = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visita=equipo),
            estado__in=['JUG', 'WO'],
            etapa='F1'
        )
        puntos = 0
        gf = 0; gc = 0
        for p in partidos:
            es_local = (p.equipo_local == equipo)
            goles_pro = p.goles_local if es_local else p.goles_visita
            goles_riv = p.goles_visita if es_local else p.goles_local
            gf += goles_pro; gc += goles_riv
            
            if goles_pro > goles_riv: puntos += 3
            elif goles_pro == goles_riv: puntos += 1
        
        gd = gf - gc
        tabla.append({'equipo': equipo, 'pts': puntos, 'gd': gd, 'gf': gf})

    # Ordenamos por Puntos > Gol Diferencia > Goles a Favor
    tabla_ordenada = sorted(tabla, key=lambda x: (x['pts'], x['gd'], x['gf']), reverse=True)

    # 2. Asignamos Grupos y Bonos
    with transaction.atomic():
        for index, fila in enumerate(tabla_ordenada):
            equipo = fila['equipo']
            posicion = index + 1
            
            equipo.puntos_bonificacion = 0 # Reset
            
            # BONOS
            if posicion == 1:
                equipo.puntos_bonificacion = 2
                messages.info(request, f'🥇 {equipo.nombre} recibe 2 puntos de bonificación.')
            elif posicion == 2:
                equipo.puntos_bonificacion = 1
                messages.info(request, f'🥈 {equipo.nombre} recibe 1 punto de bonificación.')

            # GRUPOS (Serpiente)
            # 1, 3, 5... -> A
            # 2, 4, 6... -> B
            if posicion % 2 != 0:
                equipo.grupo_fase2 = 'A'
            else:
                equipo.grupo_fase2 = 'B'
            
            equipo.save()

    messages.success(request, '✅ Fase 2 generada: Equipos divididos y bonos asignados.')
    return redirect('tabla_posiciones_f2', torneo_id=torneo.id)


# --- TABLA FASE 2 (Pares e Impares) ---
@login_required
def tabla_posiciones_f2(request, torneo_id):
    torneo = Torneo.objects.get(id=torneo_id)
    
    def calcular_grupo(letra_grupo):
        equipos_grupo = Equipo.objects.filter(torneo=torneo, grupo_fase2=letra_grupo)
        lista_tabla = []
        
        for equipo in equipos_grupo:
            # FILTRO: Solo partidos de FASE 2 ('F2')
            partidos = Partido.objects.filter(
                Q(equipo_local=equipo) | Q(equipo_visita=equipo),
                estado__in=['JUG', 'WO'],
                etapa='F2' 
            )
            
            pj=0; pg=0; pe=0; pp=0; gf=0; gc=0
            for p in partidos:
                pj+=1
                es_local = (p.equipo_local == equipo)
                goles_pro = p.goles_local if es_local else p.goles_visita
                goles_rival = p.goles_visita if es_local else p.goles_local
                gf+=goles_pro; gc+=goles_rival
                
                if goles_pro > goles_rival: pg+=1
                elif goles_pro < goles_rival: pp+=1
                else: pe+=1
            
            # AQUÍ SÍ SUMAMOS EL BONO QUE TRAEN DE FASE 1
            puntos = (pg * 3) + (pe * 1) + equipo.puntos_bonificacion
            gd = gf - gc
            
            lista_tabla.append({
                'equipo': equipo, 
                'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp,
                'gf': gf, 'gc': gc, 'gd': gd, 
                'pts': puntos,
                'bono': equipo.puntos_bonificacion
            })
        
        return sorted(lista_tabla, key=lambda x: (x['pts'], x['gd']), reverse=True)

    tabla_a = calcular_grupo('A')
    tabla_b = calcular_grupo('B')

    return render(request, 'core/tabla_posiciones_f2.html', {
        'torneo': torneo, 
        'tabla_a': tabla_a, 
        'tabla_b': tabla_b,
        'fase': 2
    })


def seleccionar_reporte(request):
    """
    Vista pública para que los usuarios elijan de qué torneo quieren ver
    la Tabla de Posiciones, Goleadores y Tarjetas.
    """
    # Mostramos primero los torneos activos, luego los antiguos
    torneos = Torneo.objects.all().order_by('-activo', '-fecha_inicio')
    
    return render(request, 'core/seleccionar_reporte.html', {
        'torneos': torneos
    })

@login_required
def reporte_estadisticas(request, torneo_id):
    torneo = Torneo.objects.get(id=torneo_id)
    
    # 1. IDENTIFICAR ROL DEL USUARIO
    user_perfil = request.user.perfil if hasattr(request.user, 'perfil') else None
    rol = user_perfil.rol if user_perfil else 'FAN'

    # 2. TOP 15 GOLEADORES (SECCIÓN PÚBLICA)
    goleadores = DetallePartido.objects.filter(partido__torneo=torneo, tipo='GOL').values(
        'jugador__nombres', 'jugador__equipo__nombre', 'jugador__equipo__escudo'
    ).annotate(total_goles=Count('id')).order_by('-total_goles')[:15]

    # 3. TABLA DE POSICIONES FASE 1 (SECCIÓN PÚBLICA)
    equipos_todos = Equipo.objects.filter(torneo=torneo)
    tabla = []
    for equipo in equipos_todos:
        partidos = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visita=equipo),
            estado__in=['JUG', 'WO'],
            etapa='F1'
        )
        pj = 0; pg = 0; pe = 0; pp = 0; gf = 0; gc = 0
        for p in partidos:
            pj += 1
            es_local = (p.equipo_local == equipo)
            goles_pro = p.goles_local if es_local else p.goles_visita
            goles_riv = p.goles_visita if es_local else p.goles_local
            gf += goles_pro
            gc += goles_riv
            if goles_pro > goles_riv: pg += 1
            elif goles_pro < goles_riv: pp += 1
            else: pe += 1
        
        tabla.append({
            'equipo': equipo, 'pj': pj, 'pg': pg, 'pe': pe, 'pp': pp,
            'gf': gf, 'gc': gc, 'gd': gf - gc, 'pts': (pg * 3) + (pe * 1)
        })
    tabla_ordenada = sorted(tabla, key=lambda x: (x['pts'], x['gd']), reverse=True)

    # 4. FILTRO DE PRIVACIDAD ESTRICTA (SÓLO EQUIPOS PERMITIDOS)
    if rol in ['ORG', 'VOC']:
        equipos_permitidos = equipos_todos # Admin y Vocal ven todos los equipos
    elif rol == 'DIR':
        equipos_permitidos = Equipo.objects.filter(torneo=torneo, dirigente=request.user) # Dirigente solo ve el suyo
    else:
        equipos_permitidos = Equipo.objects.none() # Fans no ven nada de disciplina

    # 5. SANCIONES ACTIVAS (SECCIÓN PRIVADA)
    sancionados_activos = []
    
    # Solo calculamos sanciones si el usuario tiene permiso de ver algún equipo
    if equipos_permitidos.exists():
        jugadores_con_faltas = Jugador.objects.filter(
            equipo__in=equipos_permitidos, # <-- AQUÍ APLICAMOS LA PRIVACIDAD DE EQUIPOS
            detallepartido__partido__torneo=torneo,
            detallepartido__tipo__in=['TA', 'TR', 'DA', 'AZUL', 'EBRI']
        ).distinct()

        for j in jugadores_con_faltas:
            detalles = DetallePartido.objects.filter(jugador=j, partido__torneo=torneo).order_by('partido__fecha_hora')
            ta_acumuladas = detalles.filter(tipo='TA').count()
            partidos_suspension = 0
            motivo = ""; fecha_incidente = None

            if ta_acumuladas > 0 and ta_acumuladas % 4 == 0:
                partidos_suspension = 1
                motivo = "Acumulación 4 TA"
                ultimo_evento = detalles.filter(tipo='TA').last()
                fecha_incidente = ultimo_evento.partido.fecha_hora

            ultimo_tr = detalles.filter(tipo='TR').last()
            if ultimo_tr:
                partidos_suspension = 2
                motivo = "Roja Directa"
                fecha_incidente = ultimo_tr.partido.fecha_hora
                if detalles.filter(tipo='TR').count() >= 2:
                    partidos_suspension = 999
                    motivo = "EXPULSADO DEL TORNEO (Reincidencia TR)"

            otras_faltas = detalles.filter(tipo__in=['DA', 'AZUL', 'EBRI']).last()
            if otras_faltas and (not ultimo_tr or otras_faltas.partido.fecha_hora > ultimo_tr.partido.fecha_hora):
                partidos_suspension = 1
                motivo = f"Sanción por {otras_faltas.get_tipo_display()}"
                fecha_incidente = otras_faltas.partido.fecha_hora

            if partidos_suspension > 0 and fecha_incidente:
                partidos_posteriores = Partido.objects.filter(
                    Q(equipo_local=j.equipo) | Q(equipo_visita=j.equipo),
                    torneo=torneo, estado='JUG', fecha_hora__gt=fecha_incidente
                ).count()

                if partidos_posteriores < partidos_suspension:
                    debe = partidos_suspension - partidos_posteriores
                    sancionados_activos.append({
                        'jugador': j, 'motivo': motivo,
                        'restantes': "Expulsado" if partidos_suspension == 999 else f"Debe {debe} fecha(s)",
                        'fecha': fecha_incidente
                    })

    # 6. DETALLE POR EQUIPO (SECCIÓN PRIVADA)
    equipo_id = request.GET.get('equipo')
    jugadores_detalle = []
    equipo_seleccionado = None

    if equipo_id and equipo_id.isdigit():
        try:
            # Seguridad: Usamos 'equipos_permitidos' para que un DIR no pueda ver otro equipo alterando la URL
            equipo_seleccionado = equipos_permitidos.get(id=equipo_id)
            roster = Jugador.objects.filter(equipo=equipo_seleccionado)
            for j in roster:
                stats = DetallePartido.objects.filter(jugador=j, partido__torneo=torneo)
                jugadores_detalle.append({
                    'nombre': j.nombres,
                    'asis': stats.filter(tipo='ASIS').count(),
                    'ta': stats.filter(tipo='TA').count(),
                    'tr': stats.filter(tipo='TR').count(),
                    'goles': stats.filter(tipo='GOL').count()
                })
        except Equipo.DoesNotExist:
            # Si intenta acceder a un ID que no le pertenece o no existe
            equipo_seleccionado = None

    return render(request, 'core/reporte_estadisticas.html', {
        'torneo': torneo, 
        'goleadores': goleadores, 
        'tabla_posiciones': tabla_ordenada,
        'equipos_permitidos': equipos_permitidos,
        'equipo_seleccionado': equipo_seleccionado, 
        'jugadores_detalle': jugadores_detalle,
        'sancionados_activos': sancionados_activos,
        'rol': rol
    })



@login_required
def tabla_goleadores(request, torneo_id):
    torneo = Torneo.objects.get(id=torneo_id)
    goleadores = DetallePartido.objects.filter(partido__torneo=torneo, tipo='GOL').values(
        'jugador__nombres', 'jugador__equipo__nombre', 'jugador__equipo__escudo'
    ).annotate(total_goles=Count('id')).order_by('-total_goles')[:10]
    return render(request, 'core/tabla_goleadores.html', {'torneo': torneo, 'goleadores': goleadores})


# =========================================================
# 5. GENERACIÓN DE PDF (ACTA) (ACCESO VOCAL Y ADMIN)
# =========================================================

@login_required
@user_passes_test(es_vocal_o_admin) # <--- PERMISO EXPANDIDO
def generar_acta_pdf(request, partido_id):
    partido = Partido.objects.get(id=partido_id)
    detalles = DetallePartido.objects.filter(partido=partido).select_related('jugador')
    
    asistencias_local = detalles.filter(tipo='ASIS', jugador__equipo=partido.equipo_local)
    asistencias_visita = detalles.filter(tipo='ASIS', jugador__equipo=partido.equipo_visita)
    goles = detalles.filter(tipo='GOL')
    tarjetas = detalles.filter(tipo__in=['TA', 'TR', 'DA', 'AZUL', 'EBRI'])

    template_path = 'core/acta_partido_pdf.html'
    context = {
        'partido': partido,
        'asistencias_local': asistencias_local,
        'asistencias_visita': asistencias_visita,
        'goles': goles,
        'tarjetas': tarjetas,
    }
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Acta_{partido.id}.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('Error al generar PDF <pre>' + html + '</pre>')
    return response


# =========================================================
# 6. FINANZAS Y PAGOS
# =========================================================

@login_required
@user_passes_test(es_organizador)
def gestionar_finanzas(request):
    """
    Vista simplificada: Solo calcula ingresos y muestra historial.
    Sin configuraciones de IVA ni formularios complejos.
    """
    
    # 1. Calcular Ingresos por Alquiler de Canchas (Reservas normales)
    # Sumamos el precio_total de todas las reservas ACTIVAS que NO sean torneos
    total_reservas = ReservaCancha.objects.filter(estado='ACTIVA', es_torneo=False).aggregate(Sum('precio_total'))['precio_total__sum'] or 0

    # 2. Calcular Ingresos por Sanciones (Multas y Tarjetas)
    # Sumamos lo que ya pagaron
    sanciones_pagadas = Sancion.objects.filter(pagada=True).aggregate(Sum('monto'))['monto__sum'] or 0
    
    # Sumamos lo que deben (Pendiente)
    sanciones_pendientes = Sancion.objects.filter(pagada=False).aggregate(Sum('monto'))['monto__sum'] or 0

    # 3. Obtener el historial completo para la tabla
    lista_sanciones = Sancion.objects.all().select_related('equipo').order_by('pagada', '-fecha_creacion')

    # 4. Enviar todo al HTML
    ctx = {
        'total_caja': total_reservas + sanciones_pagadas, # Dinero real en mano
        'ingreso_canchas': total_reservas,
        'ingreso_multas': sanciones_pagadas,
        'por_cobrar': sanciones_pendientes,
        'sanciones': lista_sanciones
    }
    
    return render(request, 'core/gestionar_finanzas.html', ctx)

@login_required
@user_passes_test(es_organizador)
def registrar_pago(request):
    # 1. Obtenemos el ID del equipo desde la URL (ej: ?equipo=5)
    equipo_id = request.GET.get('equipo')
    
    # Buscamos el objeto Equipo real. Si no existe, da error 404 (seguridad)
    equipo = get_object_or_404(Equipo, id=equipo_id) if equipo_id else None

    if request.method == 'POST':
        form = PagoForm(request.POST, request.FILES)
        
        if form.is_valid():
        
            pago = form.save(commit=False)
            if equipo:
                pago.equipo = equipo
                
            pago.save() 
            
            messages.success(request, f'🤑 Pago de ${pago.monto} registrado para {pago.equipo.nombre}')
            return redirect('gestionar_finanzas')
        else:
            print("Errores del formulario:", form.errors)
            messages.error(request, "Error en el formulario. Revisa los campos.")
            
    else:
        # Pre-cargamos el equipo en el formulario visualmente
        initial_data = {'equipo': equipo} if equipo else {}
        form = PagoForm(initial=initial_data)

    # 4. Pasamos 'equipo' al contexto para que el HTML muestre el nombre
    return render(request, 'core/registrar_pago.html', {
        'form': form, 
        'equipo': equipo 
    })



# =========================================================
# 7. REGISTRO PÚBLICO
# =========================================================

def registro_publico(request):
    # Si el usuario ya entró, lo mandamos al dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegistroPublicoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Cuenta creada con éxito! Por favor inicia sesión.')
            return redirect('login') 
    else:
        form = RegistroPublicoForm()
    
    return render(request, 'registration/registro_publico.html', {'form': form})

@login_required
@user_passes_test(es_organizador)
def historial_pagos_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    # Buscamos todos los pagos de este equipo, del más reciente al más antiguo
    pagos = Pago.objects.filter(equipo=equipo).order_by('-fecha', '-id')
    
    return render(request, 'core/historial_pagos.html', {
        'equipo': equipo,
        'pagos': pagos
    })

def generar_recibo_pago_pdf(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    
    template_path = 'core/acta_pago_pdf.html'
    context = {'pago': pago}
    
    response = HttpResponse(content_type='application/pdf')
    # "filename" es el nombre con el que se descarga
    response['Content-Disposition'] = f'filename="Recibo_Pago_{pago.id}_{pago.equipo.nombre}.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    # Crear el PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('Error al generar el PDF <pre>' + html + '</pre>')
    return response




def reservar_cancha(request):
    """ Grilla de reservas actualizada: $5, 3PM a 9PM y Mínimo Mañana """
    
    # Por defecto, mostramos "Mañana"
    manana = timezone.now().date() + timedelta(days=1)
    
    fecha_str = request.GET.get('fecha')
    if fecha_str:
        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            if fecha_consulta <= timezone.now().date():
                messages.warning(request, "Recuerda: Solo se puede reservar con 1 día de anticipación.")
                fecha_consulta = manana
        except ValueError:
            fecha_consulta = manana
    else:
        fecha_consulta = manana

    precio_fijo_hora = 5.00  # NUEVO PRECIO: $5.00

    horarios_disponibles = []
    apertura = 15 # 3 PM
    cierre = 21   # 9 PM
    
    # 🔥 CAMBIO AQUÍ: Excluimos las canceladas. Así, las ACTIVAS y las PENDIENTES bloquean la grilla.
    reservas_del_dia = ReservaCancha.objects.filter(fecha=fecha_consulta).exclude(estado='CANCELADA')

    for hora in range(apertura, cierre):
        hora_inicio = time(hora, 0)
        hora_fin = time(hora + 1, 0)
        ocupado = False
        reserva_info = None
        
        for r in reservas_del_dia:
            if r.hora_inicio < hora_fin and r.hora_fin > hora_inicio:
                ocupado = True
                reserva_info = r
                break
        
        # 🔥 NUEVA LÓGICA DE ESTADOS VISUALES
        estado = 'LIBRE'
        if ocupado:
            if reserva_info.es_torneo: 
                estado = 'TORNEO'
            elif reserva_info.estado == 'PENDIENTE':
                estado = 'PENDIENTE' # <-- ¡AQUÍ ESTÁ EL TRUCO!
            else:
                estado = 'OCUPADO'

        horarios_disponibles.append({
            'hora_mostrar': f"{hora}:00 - {hora+1}:00",
            'valor_inicio': f"{hora:02d}:00",
            'valor_fin': f"{hora+1:02d}:00",
            'estado': estado
        })
    if request.method == 'POST':
        form = ReservaCanchaForm(request.POST)
        if form.is_valid():
            datos_reserva = request.POST.copy()
            datos_reserva['precio_fijo'] = precio_fijo_hora
            request.session['reserva_pendiente'] = datos_reserva
            return redirect('checkout_pago') # Nos saltamos el carrito y vamos directo a confirmar
            
    else:
        initial_data = request.session.get('reserva_pendiente', {'fecha': fecha_consulta})
        form = ReservaCanchaForm(initial=initial_data)

    return render(request, 'core/reservar_cancha.html', {
        'form': form, 'horarios': horarios_disponibles,
        'fecha_seleccionada': fecha_consulta, 'precio_hora': precio_fijo_hora,
        'manana': manana # Para bloquear el calendario HTML
    })

@login_required
def checkout_pago(request):
    """ Confirmación y guardado como PENDIENTE sin sacar al usuario de la web """
    datos = request.session.get('reserva_pendiente')
    
    if not datos:
        return redirect('reservar_cancha')

    if request.method == 'POST':
        form = ReservaCanchaForm(datos)
        if form.is_valid():
            reserva = form.save(commit=False)
            reserva.usuario = request.user
            reserva.estado = 'PENDIENTE' 
            reserva.pagado = False 
            
            from decimal import Decimal
            reserva.precio_total = Decimal(str(datos.get('precio_fijo', 5.00)))
            reserva.monto_reembolso = Decimal('0.00')
            
            reserva.save() 
            
            # Limpiamos el carrito
            del request.session['reserva_pendiente']
            
            # Mensaje de éxito y regresamos a la pantalla de "Mis Reservas"
            messages.success(request, '✅ ¡Tu turno se ha guardado como PENDIENTE! Recuerda enviar el comprobante para no perderlo.')
            return redirect('mis_reservas')
            
    return render(request, 'core/checkout.html', {'datos': datos})



@login_required
def aprobar_reserva_admin(request, reserva_id):
    """ 🔥 NUEVA FUNCIÓN: El administrador aprueba el turno tras confirmar el pago en WhatsApp """
    if request.user.perfil.rol != 'ORG':
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('dashboard')
        
    reserva = get_object_or_404(ReservaCancha, id=reserva_id)
    reserva.estado = 'ACTIVA'
    reserva.pagado = True  # Al aprobarla, damos por hecho que recibiste el dinero o comprobante
    reserva.save()
    
    messages.success(request, f'✅ Turno de {reserva.usuario.first_name} aprobado y confirmado exitosamente.')
    return redirect('dashboard')

@login_required
def mis_reservas(request):
    """ Historial de compras del cliente """
    reservas = ReservaCancha.objects.filter(usuario=request.user).order_by('-fecha')
    return render(request, 'core/mis_reservas.html', {'reservas': reservas})

#  VITRINA DE TORNEOS (Público/Dirigentes)
def ver_torneos_activos(request):
    """ Muestra los torneos donde uno puede inscribirse """
    
    # 1. Buscamos torneos abiertos
    torneos = Torneo.objects.filter(activo=True, inscripcion_abierta=True)
    
    # 2. Calculamos en cuáles YA está inscrito el usuario (para bloquear el botón)
    mis_torneos_ids = []
    if request.user.is_authenticated:
        # Obtenemos solo los IDs de los torneos donde este usuario es dirigente
        mis_torneos_ids = list(Equipo.objects.filter(dirigente=request.user).values_list('torneo_id', flat=True))

    return render(request, 'core/ver_torneos_activos.html', {
        'torneos': torneos,
        'mis_torneos_ids': mis_torneos_ids # <--- Lista clave para el HTML
    })


#  SOLICITUD DE INSCRIPCIÓN (El Dirigente crea su equipo)
@login_required
def solicitar_inscripcion(request, torneo_id):
    torneo = get_object_or_404(Torneo, id=torneo_id)
    
    # A) Verificar si ya tiene equipo en este torneo para no duplicar
    ya_inscrito = Equipo.objects.filter(torneo=torneo, dirigente=request.user).exists()
    if ya_inscrito:
        messages.warning(request, 'Ya tienes un equipo inscrito en este torneo.')
        return redirect('ver_torneos_activos') # Lo devolvemos a la vitrina

    # B) Procesar el Formulario
    if request.method == 'POST':
        form = EquipoForm(request.POST, request.FILES)
        if form.is_valid():
            equipo = form.save(commit=False)
            equipo.torneo = torneo
            equipo.dirigente = request.user
            equipo.estado_inscripcion = 'PENDIENTE' # <--- ESTADO CLAVE
            equipo.save()
            
            # C) Actualizar Rol: Si era solo FAN, ahora es DIRIGENTE
            if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'FAN':
                request.user.perfil.rol = 'DIR'
                request.user.perfil.save()
                
            messages.success(request, '✅ Solicitud enviada. Tu cupo está reservado pendiente de aprobación.')
            
            # D) REDIRECCIÓN INTELIGENTE: Volver a la vitrina para ver el estado "Pendiente"
            return redirect('ver_torneos_activos') 
    else:
        form = EquipoForm()

    return render(request, 'core/solicitar_inscripcion.html', {'form': form, 'torneo': torneo})


# 3. GESTIÓN DE SOLICITUDES (Solo Organizador)
@login_required
@user_passes_test(es_organizador)
def gestionar_solicitudes(request):
    # Buscamos equipos que estén "PENDIENTE"
    solicitudes = Equipo.objects.filter(estado_inscripcion='PENDIENTE').select_related('torneo', 'dirigente')
    
    if request.method == 'POST':
        equipo_id = request.POST.get('equipo_id')
        accion = request.POST.get('accion') # 'APROBAR' o 'RECHAZAR'
        
        equipo = get_object_or_404(Equipo, id=equipo_id)
        
        if accion == 'APROBAR':
            equipo.estado_inscripcion = 'APROBADO'
            equipo.save()
            
            # --- LÓGICA LIMPIA (PRECIO DIRECTO) ---
            # Tomamos el precio directo configurado en el torneo
            precio_inscripcion = equipo.torneo.costo_inscripcion
            
            # Creamos la deuda en Caja/Sanciones
            Sancion.objects.create(
                torneo=equipo.torneo,
                equipo=equipo,
                tipo='ADMIN', # Tipo Administrativo (Inscripción)
                monto=precio_inscripcion, # Precio exacto, sin cálculos extras
                descripcion=f"Inscripción al Torneo {equipo.torneo.nombre}",
                pagada=False # ¡Nace como deuda pendiente!
            )
            
            messages.success(request, f'✅ {equipo.nombre} aprobado. Se generó deuda de inscripción por ${precio_inscripcion}')
            
        elif accion == 'RECHAZAR':
            equipo.estado_inscripcion = 'RECHAZADO'
            equipo.save()
            messages.warning(request, f'Solicitud de {equipo.nombre} rechazada.')
            
        return redirect('gestionar_solicitudes')

    return render(request, 'core/gestionar_solicitudes.html', {'solicitudes': solicitudes})


# --- LOGICA DEL CARRITO Y PAGO ---

def ver_carrito(request):
    """ Muestra el resumen de lo que el usuario quiere comprar (Amazon Style) """
    reserva_session = request.session.get('reserva_pendiente')
    
    if not reserva_session:
        messages.info(request, "Tu carrito está vacío.")
        return redirect('reservar_cancha')

    # Recalculamos visualmente los datos para mostrarlos
    ctx = {
        'fecha': reserva_session.get('fecha'),
        'inicio': reserva_session.get('hora_inicio'),
        'fin': reserva_session.get('hora_fin'),
        # Nota: En un caso real recalcularíamos el precio aquí para seguridad
    }
    return render(request, 'core/carrito.html', ctx)



@login_required
def cancelar_reserva(request, reserva_id):
    reserva = get_object_or_404(ReservaCancha, id=reserva_id)
    
    # Seguridad: Solo el dueño o el admin pueden cancelar
    if request.user != reserva.usuario and request.user.perfil.rol != 'ORG':
        messages.error(request, "No tienes permiso para cancelar esta reserva.")
        return redirect('mis_reservas')

    # Lógica de Fechas
    fecha_reserva = reserva.fecha # Date
    fecha_hoy = timezone.now().date()
    dias_faltantes = (fecha_reserva - fecha_hoy).days
    
    multa = 0
    mensaje = ""

    # REGLA: Si faltan 2 días o menos (o es hoy), multa del 50%
    if dias_faltantes <= 2:
        multa = float(reserva.precio_total) * 0.50
        mensaje = f"⚠️ Cancelación tardía (faltan {dias_faltantes} días). Se aplicó multa del 50%."
    else:
        multa = 0
        mensaje = "✅ Cancelación a tiempo. Reembolso completo."

    reembolso = float(reserva.precio_total) - multa

    # Ejecutar Cancelación
    if request.method == 'POST':
        reserva.estado = 'CANCELADA'
        reserva.monto_reembolso = reembolso
        reserva.save()
        messages.info(request, f"Reserva Cancelada. {mensaje} Reembolso: ${reembolso}")
        return redirect('mis_reservas')

    return render(request, 'core/confirmar_cancelacion.html', {
        'objeto': reserva, 
        'tipo': 'Reserva de Cancha',
        'multa': multa,
        'reembolso': reembolso,
        'dias': dias_faltantes
    })

@login_required
def cancelar_inscripcion_equipo(request, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    
    if request.user != equipo.dirigente and request.user.perfil.rol != 'ORG':
        return redirect('dashboard')

    precio_inscripcion = float(equipo.torneo.costo_inscripcion)
    multa = 0
    
    # REGLA: Si ya fue aprobado, multa del 25%
    if equipo.estado_inscripcion == 'APROBADO':
        multa = precio_inscripcion * 0.25
        mensaje = "⚠️ Equipo ya aprobado. Se retiene el 25% por gastos administrativos."
    else:
        # Si está PENDIENTE
        multa = 0
        mensaje = "✅ Solicitud cancelada antes de aprobación. Sin costo."

    reembolso = precio_inscripcion - multa

    if request.method == 'POST':
        # En inscripciones, solemos borrar el equipo o cambiar estado
        # Para historial, mejor cambiamos estado a RECHAZADO (o creamos uno CANCELADO)
        equipo.estado_inscripcion = 'RECHAZADO' 
        equipo.monto_reembolso = reembolso
        equipo.save()
        messages.info(request, f"Inscripción Cancelada. {mensaje} Reembolso: ${reembolso}")
        return redirect('ver_torneos_activos')

    return render(request, 'core/confirmar_cancelacion.html', {
        'objeto': equipo,
        'tipo': f"Inscripción Equipo {equipo.nombre}",
        'multa': multa,
        'reembolso': reembolso,
        'extra_info': "Estado actual: " + equipo.get_estado_inscripcion_display()
    })

@login_required
def cobrar_sancion(request, sancion_id):
    # Solo el admin puede cobrar
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')
        
    sancion = get_object_or_404(Sancion, id=sancion_id)
    sancion.pagada = True
    sancion.save()
    
    messages.success(request, f"💰 Cobro registrado: ${sancion.monto} a {sancion.equipo.nombre}")
    return redirect('dashboard')


@login_required
def gestionar_finanzas(request):
    """ Vista de Caja y Sanciones para el Organizador """
    # 1. Seguridad: Solo ORG
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')
    
    # 2. Calcular Ingresos por RESERVAS (Canchas alquiladas)
    # Asumimos que si está ACTIVA y NO es torneo, es un alquiler pagado (o puedes usar el campo .pagado si lo agregamos)
    total_reservas = ReservaCancha.objects.filter(estado='ACTIVA', es_torneo=False).aggregate(Sum('precio_total'))['precio_total__sum'] or 0
    
    # 3. Calcular Ingresos por SANCIONES
    sanciones_pagadas = Sancion.objects.filter(pagada=True).aggregate(Sum('monto'))['monto__sum'] or 0
    sanciones_pendientes = Sancion.objects.filter(pagada=False).aggregate(Sum('monto'))['monto__sum'] or 0
    
    # 4. Lista de Sanciones para la tabla (Las pendientes primero)
    lista_sanciones = Sancion.objects.all().select_related('equipo').order_by('pagada', '-fecha_creacion')

    ctx = {
        'total_caja': total_reservas + sanciones_pagadas,
        'ingreso_canchas': total_reservas,
        'ingreso_multas': sanciones_pagadas,
        'por_cobrar': sanciones_pendientes,
        'sanciones': lista_sanciones
    }
    return render(request, 'core/gestionar_finanzas.html', ctx)


@login_required
def admin_gestion_jugadores(request):
    """ Vista para que el Organizador vea TODOS los jugadores de todos los equipos """
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')
        
    query = request.GET.get('q')
    jugadores = Jugador.objects.all().select_related('equipo').order_by('equipo', 'dorsal')
    
    if query:
        jugadores = jugadores.filter(
            Q(nombre__icontains=query) | 
            Q(equipo__nombre__icontains=query) |
            Q(cedula__icontains=query)
        )

    return render(request, 'core/admin_jugadores.html', {'jugadores': jugadores})

@login_required
def admin_gestion_usuarios(request):
    """ Vista para administrar Usuarios del sistema """
    
    # 1. Seguridad: Solo Organizador
    if request.user.perfil.rol != 'ORG':
        return redirect('dashboard')

    # 2. PROCESAR CAMBIO DE ROL (ESTO ES LO QUE FALTABA)
    if request.method == 'POST':
        perfil_id = request.POST.get('perfil_id')
        nuevo_rol = request.POST.get('nuevo_rol')
        
        if perfil_id and nuevo_rol:
            # Buscamos el perfil específico usando el ID que envió el formulario
            perfil_usuario = get_object_or_404(Perfil, id=perfil_id)
            
            # Evitar que el admin se quite permisos a sí mismo por error
            if perfil_usuario.usuario == request.user:
                messages.error(request, "No puedes cambiar tu propio rol aquí.")
            else:
                perfil_usuario.rol = nuevo_rol
                perfil_usuario.save()
                messages.success(request, f'Rol de "{perfil_usuario.usuario.username}" actualizado a {perfil_usuario.get_rol_display()}.')
            
            # Recargamos la página para ver el cambio
            return redirect('admin_gestion_usuarios')

    # 3. Mostrar la lista
    usuarios = User.objects.all().select_related('perfil').order_by('-date_joined')
    
    return render(request, 'core/admin_usuarios.html', {'usuarios': usuarios})

@login_required
def registrar_incidencia(request, partido_id):
    """
    Registra goles y tarjetas (Versión Limpia - SIN IVA).
    Si es Tarjeta, genera la deuda basada en el costo directo del Torneo.
    """
    partido = get_object_or_404(Partido, id=partido_id)
    
    # Seguridad: Solo Vocal (VOC) u Organizador (ORG)
    if request.user.perfil.rol not in ['VOC', 'ORG']:
        messages.error(request, "No tienes permiso para realizar esta acción.")
        return redirect('dashboard')

    if request.method == 'POST':
        jugador_id = request.POST.get('jugador')
        tipo_evento = request.POST.get('tipo') # 'GOL', 'AMARILLA', 'ROJA'
        minuto = request.POST.get('minuto', 0)
        
        jugador = get_object_or_404(Jugador, id=jugador_id)

        # 1. GUARDAR EL EVENTO EN EL ACTA (Estadística Deportiva)
        DetallePartido.objects.create(
            partido=partido,
            jugador=jugador,
            tipo=tipo_evento,
            minuto=int(minuto) if minuto else 0
        )

        # 2. LÓGICA DE SANCIONES ECONÓMICAS (Finanzas Limpias)
        if tipo_evento in ['AMARILLA', 'ROJA']:
            
            # Obtener Precio Directo del Torneo (Sin cálculos de IVA)
            monto_sancion = 0.0
            if tipo_evento == 'AMARILLA':
                monto_sancion = float(partido.torneo.costo_amarilla)
            elif tipo_evento == 'ROJA':
                monto_sancion = float(partido.torneo.costo_roja)
            
            if monto_sancion > 0:
                # Crear la Deuda Directa
                Sancion.objects.create(
                    torneo=partido.torneo,
                    equipo=jugador.equipo,
                    jugador=jugador,
                    partido=partido,
                    tipo=tipo_evento,
                    monto=monto_sancion, # Cobro neto
                    pagada=False,
                    descripcion=f"Min {minuto}: {tipo_evento} en partido vs {'Visita' if jugador.equipo == partido.equipo_local else 'Local'}"
                )
                
                messages.warning(request, f"⚖️ Sanción registrada: ${monto_sancion} cargados a {jugador.equipo.nombre}")
        
        elif tipo_evento == 'GOL':
            # Actualizar marcador del partido
            if jugador.equipo == partido.equipo_local:
                partido.goles_local += 1
            else:
                partido.goles_visita += 1
            partido.save()
            
            messages.success(request, f"⚽ ¡Gol de {jugador.nombres}!")

    # Redirigir siempre de vuelta a la gestión de vocalía
    return redirect('gestionar_vocalia', partido_id=partido.id)