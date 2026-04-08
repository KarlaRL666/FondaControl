from datetime import date, datetime, timedelta


def _normalizar_valor_mongo(valor):
    if isinstance(valor, (datetime, date)):
        return valor.strftime('%Y-%m-%d %H:%M:%S') if isinstance(valor, datetime) else valor.strftime('%Y-%m-%d')
    if isinstance(valor, dict):
        return {k: _normalizar_valor_mongo(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_normalizar_valor_mongo(item) for item in valor]
    return valor


def _obtener_ultimo_documento(mongo_db, collection_name):
    documento = mongo_db[collection_name].find_one(sort=[('fecha', -1)])
    if not documento:
        return None

    documento.pop('_id', None)
    return _normalizar_valor_mongo(documento)


def _to_float(valor):
    try:
        if valor is None:
            return 0.0
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _to_datetime(valor):
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime.combine(valor, datetime.min.time())
    if isinstance(valor, str):
        formatos = (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d',
        )
        for fmt in formatos:
            try:
                return datetime.strptime(valor[:19], fmt)
            except ValueError:
                continue
    return None


def obtener_estadisticas_ventas(mongo_db):
    try:
        stats = mongo_db.dashboard_cache.find_one(sort=[('fecha', -1)])
        if stats:
            stats.pop('_id', None)
            stats = _normalizar_valor_mongo(stats)
        return stats, None
    except Exception as e:
        return None, str(e)


def obtener_resumen_ventas(mongo_db):
    try:
        resumen = mongo_db.resumen_ventas.find_one(sort=[('fecha', -1)])
        if resumen:
            resumen.pop('_id', None)
            resumen = _normalizar_valor_mongo(resumen)
        return resumen, None
    except Exception as e:
        return None, str(e)


def obtener_ventas_por_producto(mongo_db):
    try:
        ventas_producto = list(mongo_db.ventas_por_producto.find().sort('fecha', -1).limit(10))
        for item in ventas_producto:
            item.pop('_id', None)
        return _normalizar_valor_mongo(ventas_producto), None
    except Exception as e:
        return None, str(e)


def obtener_reportes_mongo(mongo_db):
    try:
        colecciones_reporte = [
            'reporteVentas',
            'reporteCompras',
            'reporteProduccion',
            'estadisticasVentas',
            'historialActividad',
            'calificaciones',
            'calificaciones_servicio',
        ]

        reportes = {
            nombre: _obtener_ultimo_documento(mongo_db, nombre)
            for nombre in colecciones_reporte
        }

        return reportes, None
    except Exception as e:
        return None, str(e)


def obtener_metricas_bitacora_mongo(mongo_db, dias=7):
    try:
        inicio = datetime.utcnow() - timedelta(days=max(1, int(dias)))
        collection = mongo_db.bitacora_acciones

        pipeline_modulos = [
            {'$match': {'fecha': {'$gte': inicio}}},
            {'$group': {'_id': '$modulo', 'total': {'$sum': 1}}},
            {'$sort': {'total': -1}},
            {'$limit': 8},
        ]
        pipeline_metodos = [
            {'$match': {'fecha': {'$gte': inicio}}},
            {'$group': {'_id': '$metodo', 'total': {'$sum': 1}}},
            {'$sort': {'total': -1}},
        ]
        pipeline_usuarios = [
            {'$match': {'fecha': {'$gte': inicio}, 'usuario.username': {'$ne': None}}},
            {'$group': {'_id': '$usuario.username', 'total': {'$sum': 1}}},
            {'$sort': {'total': -1}},
            {'$limit': 8},
        ]
        pipeline_dias = [
            {'$match': {'fecha': {'$gte': inicio}}},
            {
                '$group': {
                    '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$fecha'}},
                    'total': {'$sum': 1},
                }
            },
            {'$sort': {'_id': 1}},
        ]

        modulos = list(collection.aggregate(pipeline_modulos))
        metodos = list(collection.aggregate(pipeline_metodos))
        usuarios = list(collection.aggregate(pipeline_usuarios))
        por_dia = list(collection.aggregate(pipeline_dias))

        return {
            'modulos': [{'nombre': item.get('_id') or 'sin-modulo', 'total': int(item.get('total') or 0)} for item in modulos],
            'metodos': [{'nombre': item.get('_id') or 'N/D', 'total': int(item.get('total') or 0)} for item in metodos],
            'usuarios': [{'nombre': item.get('_id') or 'sistema', 'total': int(item.get('total') or 0)} for item in usuarios],
            'por_dia': [{'fecha': item.get('_id'), 'total': int(item.get('total') or 0)} for item in por_dia],
        }, None
    except Exception as e:
        return None, str(e)


def obtener_resumen_ventas_mongo(mongo_db, dias=7):
    try:
        dias = max(1, int(dias or 7))
        inicio = datetime.utcnow() - timedelta(days=dias)

        subtotal_acumulado = 0.0
        total_acumulado = 0.0
        ventas_contadas = 0
        ultima_fecha = None

        cursor = mongo_db.reporteVentas.find({}, {'_id': 0, 'subtotal': 1, 'total': 1, 'fecha': 1})
        for doc in cursor:
            fecha_doc = _to_datetime(doc.get('fecha'))
            if fecha_doc and fecha_doc < inicio:
                continue

            subtotal_acumulado += _to_float(doc.get('subtotal'))
            total_acumulado += _to_float(doc.get('total'))
            ventas_contadas += 1

            if fecha_doc and (ultima_fecha is None or fecha_doc > ultima_fecha):
                ultima_fecha = fecha_doc

        return {
            'periodo_dias': dias,
            'ventas_contadas': ventas_contadas,
            'subtotal_acumulado': round(subtotal_acumulado, 2),
            'total_acumulado': round(total_acumulado, 2),
            'ticket_promedio': round((total_acumulado / ventas_contadas), 2) if ventas_contadas else 0.0,
            'ultima_fecha': ultima_fecha.strftime('%Y-%m-%d %H:%M:%S') if ultima_fecha else 'N/D',
        }, None
    except Exception as e:
        return None, str(e)