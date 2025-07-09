from datetime import datetime
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from dateutil import parser
from io import BytesIO
from reportlab.pdfgen import canvas
import re

app = Flask(__name__)
CORS(app)

# Conexión a MongoDB
mongo_uri = "mongodb+srv://pobando:patricio7@cluster0.f3tc9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
try:
    client = MongoClient(mongo_uri)
    db = client['InventarioFacturacion']
    productos_collection = db['productos']
    clientes_collection = db['clientes']
    facturas_collection = db['facturas']
    print("Conexión exitosa a MongoDB!")
except Exception as e:
    print(f"Error al conectar a MongoDB: {e}")
    exit()

# ---------------------- Helper Functions ----------------------

def generar_numero_factura():
    ultima_factura = facturas_collection.find_one({}, sort=[('invoiceNumber', -1)])
    
    if not ultima_factura:
        return 'FAC-001-0001'
    
    partes = ultima_factura['invoiceNumber'].split('-')
    if len(partes) == 3:
        try:
            secuencia = int(partes[2]) + 1
            return f'FAC-{partes[1]}-{str(secuencia).zfill(4)}'
        except:
            pass
    
    total_facturas = facturas_collection.count_documents({})
    return f'FAC-001-{str(total_facturas + 1).zfill(4)}'

def validar_identificacion(identification):
    """Valida que la identificación tenga entre 8 y 13 dígitos"""
    return re.match(r'^\d{8,13}$', identification)

def validar_email(email):
    """Valida formato básico de email"""
    return re.match(r'^[^@]+@[^@]+\.[^@]+$', email) if email else True

# ---------------------- Product Routes ----------------------

@app.route('/productos', methods=['POST'])
def crear_producto():
    try:
        data = request.get_json()
        
        required_fields = ['code', 'name', 'price', 'stock', 'minStock']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Faltan campos requeridos', 'required': required_fields}), 400
        
        if productos_collection.find_one({'code': data['code']}):
            return jsonify({'error': 'El código de producto ya existe'}), 400
        
        try:
            producto = {
                'code': data['code'],
                'name': data['name'],
                'description': data.get('description', ''),
                'category': data.get('category', ''),
                'price': float(data['price']),
                'cost': float(data.get('cost', 0)),
                'stock': int(data['stock']),
                'minStock': int(data['minStock']),
                'supplier': data.get('supplier', ''),
                'status': data.get('status', 'active'),
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
        except ValueError as e:
            return jsonify({'error': f'Error en tipos de datos: {str(e)}'}), 400
        
        result = productos_collection.insert_one(producto)
        
        return jsonify({
            'message': 'Producto creado exitosamente',
            'id': str(result.inserted_id),
            'code': producto['code']
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/productos', methods=['GET'])
def listar_productos():
    try:
        query = {}
        
        # Filtros opcionales
        status = request.args.get('status')
        if status:
            query['status'] = status
            
        categoria = request.args.get('category')
        if categoria:
            query['category'] = categoria
            
        stock_minimo = request.args.get('stock_min')
        if stock_minimo:
            query['stock'] = {'$lt': int(stock_minimo)}
        
        productos = list(productos_collection.find(query))
        
        for producto in productos:
            producto['_id'] = str(producto['_id'])
            producto['createdAt'] = producto['createdAt'].isoformat()
            producto['updatedAt'] = producto['updatedAt'].isoformat()
        
        return jsonify(productos), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/productos/<id>', methods=['GET'])
def obtener_producto(id):
    try:
        producto = productos_collection.find_one({'_id': ObjectId(id)})
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        producto['_id'] = str(producto['_id'])
        producto['createdAt'] = producto['createdAt'].isoformat()
        producto['updatedAt'] = producto['updatedAt'].isoformat()
        
        return jsonify(producto), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/productos/<id>', methods=['PUT'])
def actualizar_producto(id):
    try:
        data = request.get_json()
        
        producto = productos_collection.find_one({'_id': ObjectId(id)})
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        update_data = {
            'name': data.get('name', producto['name']),
            'description': data.get('description', producto['description']),
            'category': data.get('category', producto['category']),
            'price': float(data.get('price', producto['price'])),
            'cost': float(data.get('cost', producto['cost'])),
            'stock': int(data.get('stock', producto['stock'])),
            'minStock': int(data.get('minStock', producto['minStock'])),
            'supplier': data.get('supplier', producto['supplier']),
            'status': data.get('status', producto['status']),
            'updatedAt': datetime.utcnow()
        }
        
        productos_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )
        
        return jsonify({'message': 'Producto actualizado exitosamente'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/productos/<id>', methods=['DELETE'])
def eliminar_producto(id):
    try:
        producto = productos_collection.find_one({'_id': ObjectId(id)})
        if not producto:
            return jsonify({'error': 'Producto no encontrado'}), 404
        
        if facturas_collection.find_one({'items.product': ObjectId(id)}):
            return jsonify({
                'error': 'No se puede eliminar el producto porque está asociado a facturas'
            }), 400
        
        productos_collection.delete_one({'_id': ObjectId(id)})
        
        return jsonify({'message': 'Producto eliminado exitosamente'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------- Client Routes ----------------------

@app.route('/clientes', methods=['POST'])
def crear_cliente():
    try:
        data = request.get_json()
        
        required_fields = ['name', 'identificationType', 'identificationNumber']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Faltan campos requeridos', 'required': required_fields}), 400
        
        if not validar_identificacion(data['identificationNumber']):
            return jsonify({'error': 'Identificación inválida. Debe tener entre 8 y 13 dígitos'}), 400
        
        if clientes_collection.find_one({'identificationNumber': data['identificationNumber']}):
            return jsonify({'error': 'El cliente ya existe'}), 400
        
        if 'email' in data and not validar_email(data['email']):
            return jsonify({'error': 'Formato de email inválido'}), 400
        
        cliente = {
            'name': data['name'],
            'identificationType': data['identificationType'],
            'identificationNumber': data['identificationNumber'],
            'phone': data.get('phone', ''),
            'email': data.get('email', ''),
            'address': data.get('address', ''),
            'city': data.get('city', ''),
            'country': data.get('country', ''),
            'status': data.get('status', 'active'),
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        }
        
        result = clientes_collection.insert_one(cliente)
        
        return jsonify({
            'message': 'Cliente creado exitosamente',
            'id': str(result.inserted_id),
            'identificationNumber': cliente['identificationNumber']
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clientes', methods=['GET'])
def listar_clientes():
    try:
        query = {}
        
        # Filtros opcionales
        status = request.args.get('status')
        if status:
            query['status'] = status
            
        identificacion = request.args.get('identificationNumber')
        if identificacion:
            query['identificationNumber'] = identificacion
        
        clientes = list(clientes_collection.find(query))
        
        for cliente in clientes:
            cliente['_id'] = str(cliente['_id'])
            cliente['createdAt'] = cliente['createdAt'].isoformat()
            cliente['updatedAt'] = cliente['updatedAt'].isoformat()
        
        return jsonify(clientes), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clientes/<id>', methods=['GET'])
def obtener_cliente(id):
    try:
        cliente = clientes_collection.find_one({'_id': ObjectId(id)})
        if not cliente:
            return jsonify({'error': 'Cliente no encontrado'}), 404
        
        cliente['_id'] = str(cliente['_id'])
        cliente['createdAt'] = cliente['createdAt'].isoformat()
        cliente['updatedAt'] = cliente['updatedAt'].isoformat()
        
        return jsonify(cliente), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clientes/<id>', methods=['PUT'])
def actualizar_cliente(id):
    try:
        data = request.get_json()
        
        cliente = clientes_collection.find_one({'_id': ObjectId(id)})
        if not cliente:
            return jsonify({'error': 'Cliente no encontrado'}), 404
        
        if 'identificationNumber' in data and not validar_identificacion(data['identificationNumber']):
            return jsonify({'error': 'Identificación inválida. Debe tener entre 8 y 13 dígitos'}), 400
        
        if 'email' in data and not validar_email(data['email']):
            return jsonify({'error': 'Formato de email inválido'}), 400
        
        update_data = {
            'name': data.get('name', cliente['name']),
            'identificationType': data.get('identificationType', cliente['identificationType']),
            'identificationNumber': data.get('identificationNumber', cliente['identificationNumber']),
            'phone': data.get('phone', cliente['phone']),
            'email': data.get('email', cliente['email']),
            'address': data.get('address', cliente['address']),
            'city': data.get('city', cliente['city']),
            'country': data.get('country', cliente['country']),
            'status': data.get('status', cliente['status']),
            'updatedAt': datetime.utcnow()
        }
        
        clientes_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )
        
        return jsonify({'message': 'Cliente actualizado exitosamente'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clientes/<id>', methods=['DELETE'])
def eliminar_cliente(id):
    try:
        cliente = clientes_collection.find_one({'_id': ObjectId(id)})
        if not cliente:
            return jsonify({'error': 'Cliente no encontrado'}), 404
        
        if facturas_collection.find_one({'client': ObjectId(id)}):
            return jsonify({
                'error': 'No se puede eliminar el cliente porque tiene facturas asociadas'
            }), 400
        
        clientes_collection.delete_one({'_id': ObjectId(id)})
        
        return jsonify({'message': 'Cliente eliminado exitosamente'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------- Invoice Routes ----------------------

@app.route('/facturas', methods=['POST'])
def crear_factura():
    try:
        data = request.get_json()
        
        # Validación de campos requeridos
        required_fields = ['client', 'issueDate', 'paymentMethod', 'items']
        if not all(field in data for field in required_fields):
            missing = [f for f in required_fields if f not in data]
            return jsonify({'error': 'Faltan campos requeridos', 'missing': missing}), 400
        
        # Manejo del cliente (puede ser ObjectId o datos completos)
        client_data = data['client']
        client_id = None
        
        if isinstance(client_data, dict):
            # Es un nuevo cliente o datos para buscar
            if 'identificationNumber' in client_data:
                # Buscar cliente existente
                existing_client = clientes_collection.find_one({
                    'identificationNumber': client_data['identificationNumber']
                })
                
                if existing_client:
                    client_id = existing_client['_id']
                else:
                    # Validar datos para nuevo cliente
                    required_client_fields = ['name', 'identificationType', 'identificationNumber']
                    if not all(f in client_data for f in required_client_fields):
                        missing = [f for f in required_client_fields if f not in client_data]
                        return jsonify({
                            'error': 'Faltan datos requeridos del cliente',
                            'missing': missing
                        }), 400
                    
                    if not validar_identificacion(client_data['identificationNumber']):
                        return jsonify({'error': 'Identificación inválida. Debe tener entre 8 y 13 dígitos'}), 400
                    
                    if 'email' in client_data and not validar_email(client_data['email']):
                        return jsonify({'error': 'Formato de email inválido'}), 400
                    
                    # Crear nuevo cliente
                    nuevo_cliente = {
                        'name': client_data['name'],
                        'identificationType': client_data['identificationType'],
                        'identificationNumber': client_data['identificationNumber'],
                        'phone': client_data.get('phone', ''),
                        'email': client_data.get('email', ''),
                        'status': 'active',
                        'createdAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow()
                    }
                    result = clientes_collection.insert_one(nuevo_cliente)
                    client_id = result.inserted_id
        else:
            # Asumimos que es un ObjectId existente
            try:
                client_id = ObjectId(client_data)
                if not clientes_collection.find_one({'_id': client_id}):
                    return jsonify({'error': 'Cliente no encontrado'}), 404
            except:
                return jsonify({'error': 'ID de cliente inválido'}), 400
        
        # Validar items
        if not isinstance(data['items'], list) or len(data['items']) == 0:
            return jsonify({'error': 'La factura debe tener al menos un item'}), 400
        
        items = []
        subtotal = 0
        tax_rate = 0.12
        
        for item in data['items']:
            # Validar item
            if not all(k in item for k in ['product', 'quantity']):
                return jsonify({'error': 'Items incompletos. Se requieren product y quantity'}), 400
            
            try:
                product_id = ObjectId(item['product'])
                producto = productos_collection.find_one({'_id': product_id})
                
                if not producto:
                    return jsonify({'error': f'Producto {item["product"]} no encontrado'}), 404
                
                quantity = int(item.get('quantity', 1))
                if quantity <= 0:
                    return jsonify({'error': 'La cantidad debe ser mayor a 0'}), 400
                
                if producto['stock'] < quantity:
                    return jsonify({
                        'error': f'Stock insuficiente para {producto["name"]}. Disponible: {producto["stock"]}'
                    }), 400
                
                unit_price = float(item.get('unitPrice', producto['price']))
                discount = float(item.get('discount', 0))
                if discount < 0 or discount > 100:
                    return jsonify({'error': 'El descuento debe estar entre 0 y 100'}), 400
                
                item_subtotal = (unit_price * quantity) * (1 - discount/100)
                
                items.append({
                    'product': product_id,
                    'name': producto['name'],
                    'code': producto['code'],
                    'quantity': quantity,
                    'unitPrice': unit_price,
                    'discount': discount,
                    'subtotal': item_subtotal
                })
                
                subtotal += item_subtotal
            except ValueError as e:
                return jsonify({'error': f'Error en datos del item: {str(e)}'}), 400
        
        # Calcular impuestos y total
        tax = subtotal * tax_rate
        total = subtotal + tax
        
        # Crear factura
        factura = {
            'invoiceNumber': generar_numero_factura(),
            'client': client_id,
            'issueDate': parser.parse(data['issueDate']),
            'paymentMethod': data['paymentMethod'],
            'paymentStatus': data.get('paymentStatus', 'pending'),
            'subtotal': subtotal,
            'tax': tax,
            'discount': data.get('discount', 0),
            'total': total,
            'notes': data.get('notes', ''),
            'items': items,
            'status': data.get('status', 'issued'),
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        }
        
        # Insertar factura
        result = facturas_collection.insert_one(factura)
        
        # Actualizar stock si la factura está emitida
        if factura['status'] == 'issued':
            for item in items:
                productos_collection.update_one(
                    {'_id': item['product']},
                    {'$inc': {'stock': -item['quantity']}}
                )
        
        return jsonify({
            'message': 'Factura creada exitosamente',
            'id': str(result.inserted_id),
            'invoiceNumber': factura['invoiceNumber'],
            'total': factura['total']
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/facturas', methods=['GET'])
def listar_facturas():
    try:
        limit = int(request.args.get('limit', 5))  # Valor por defecto 5
        
        # Obtener facturas con información básica del cliente
        pipeline = [
            {"$sort": {"issueDate": -1}},
            {"$limit": limit},
            {"$lookup": {
                "from": "clientes",
                "localField": "client",
                "foreignField": "_id",
                "as": "clientDetails"
            }},
            {"$unwind": "$clientDetails"},
            {"$project": {
                "invoiceNumber": 1,
                "issueDate": 1,
                "total": 1,
                "paymentStatus": 1,
                "clientDetails.name": 1,
                "clientDetails.identificationNumber": 1
            }}
        ]
        
        facturas = list(facturas_collection.aggregate(pipeline))
        
        # Convertir ObjectId y fechas a strings
        for factura in facturas:
            factura['_id'] = str(factura['_id'])
            factura['issueDate'] = factura['issueDate'].isoformat()
            if 'client' in factura:
                factura['client'] = str(factura['client'])
        
        return jsonify(facturas), 200
        
    except Exception as e:
        app.logger.error(f'Error al listar facturas: {str(e)}')
        return jsonify({
            'error': 'Error interno al obtener facturas',
            'details': str(e)
        }), 500
    try:
        limit = int(request.args.get('limit', 10))  # Valor por defecto 10
        facturas = list(facturas_collection.find().sort('issueDate', -1).limit(limit))
        
        # Convertir ObjectId a string y formatear fechas
        for factura in facturas:
            factura['_id'] = str(factura['_id'])
            factura['issueDate'] = factura['issueDate'].isoformat()
            if 'client' in factura:
                factura['client'] = str(factura['client'])
        
        return jsonify(facturas), 200
    except Exception as e:
        app.logger.error(f'Error al listar facturas: {str(e)}')
        return jsonify({'error': 'Error interno al obtener facturas', 'details': str(e)}), 500
    try:
        # Filtros
        query = {}
        
        status = request.args.get('status')
        if status:
            query['status'] = status
            
        payment_status = request.args.get('paymentStatus')
        if payment_status:
            query['paymentStatus'] = payment_status
            
        cliente_id = request.args.get('client')
        if cliente_id:
            try:
                query['client'] = ObjectId(cliente_id)
            except:
                return jsonify({'error': 'ID de cliente inválido'}), 400
                
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        if fecha_inicio and fecha_fin:
            try:
                query['issueDate'] = {
                    '$gte': parser.parse(fecha_inicio),
                    '$lte': parser.parse(fecha_fin)
                }
            except:
                return jsonify({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400
        
        facturas = list(facturas_collection.find(query).sort('issueDate', -1))
        
        # Obtener detalles de clientes
        clientes_ids = [ObjectId(f['client']) for f in facturas]
        clientes = {str(c['_id']): c for c in clientes_collection.find({'_id': {'$in': clientes_ids}})}
        
        # Formatear respuesta
        for factura in facturas:
            factura['_id'] = str(factura['_id'])
            factura['client'] = str(factura['client'])
            factura['clientDetails'] = clientes.get(str(factura['client']), {})
            factura['issueDate'] = factura['issueDate'].isoformat()
            factura['createdAt'] = factura['createdAt'].isoformat()
            factura['updatedAt'] = factura['updatedAt'].isoformat()
            
            for item in factura['items']:
                item['product'] = str(item['product'])
        
        return jsonify(facturas), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/facturas/<id>', methods=['GET'])
def obtener_factura(id):
    try:
        factura = facturas_collection.find_one({'_id': ObjectId(id)})
        if not factura:
            return jsonify({'error': 'Factura no encontrada'}), 404
        
        cliente = clientes_collection.find_one({'_id': factura['client']})
        
        factura['_id'] = str(factura['_id'])
        factura['client'] = str(factura['client'])
        factura['clientDetails'] = {
            'name': cliente['name'],
            'identificationNumber': cliente['identificationNumber'],
            'phone': cliente.get('phone', ''),
            'email': cliente.get('email', '')
        } if cliente else {}
        factura['issueDate'] = factura['issueDate'].isoformat()
        factura['createdAt'] = factura['createdAt'].isoformat()
        factura['updatedAt'] = factura['updatedAt'].isoformat()
        
        # Obtener detalles completos de productos
        productos_ids = [ObjectId(item['product']) for item in factura['items']]
        productos = {str(p['_id']): p for p in productos_collection.find({'_id': {'$in': productos_ids}})}
        
        for item in factura['items']:
            item['product'] = str(item['product'])
            item['productDetails'] = productos.get(item['product'], {})
        
        return jsonify(factura), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/facturas/<id>', methods=['PUT'])
def actualizar_factura(id):
    try:
        data = request.get_json()
        
        factura = facturas_collection.find_one({'_id': ObjectId(id)})
        if not factura:
            return jsonify({'error': 'Factura no encontrada'}), 404
        
        # Solo permitir actualizar ciertos campos
        allowed_fields = ['paymentStatus', 'notes', 'status']
        update_data = {
            'updatedAt': datetime.utcnow()
        }
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        # Validar cambio de estado
        if 'status' in update_data:
            if factura['status'] == 'issued' and update_data['status'] == 'cancelled':
                # Anular factura - devolver stock
                for item in factura['items']:
                    productos_collection.update_one(
                        {'_id': item['product']},
                        {'$inc': {'stock': item['quantity']}}
                    )
                update_data['paymentStatus'] = 'void'
            elif factura['status'] == 'draft' and update_data['status'] == 'issued':
                # Emitir factura - descontar stock
                for item in factura['items']:
                    productos_collection.update_one(
                        {'_id': item['product']},
                        {'$inc': {'stock': -item['quantity']}}
                    )
        
        facturas_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )
        
        return jsonify({'message': 'Factura actualizada exitosamente'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/facturas/<id>/pdf', methods=['GET'])
def generar_pdf_factura(id):
    try:
        factura = facturas_collection.find_one({'_id': ObjectId(id)})
        if not factura:
            return jsonify({'error': 'Factura no encontrada'}), 404
        
        cliente = clientes_collection.find_one({'_id': factura['client']})
        
        # Crear PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        
        # Encabezado
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 800, "FACTURA ELECTRÓNICA")
        p.setFont("Helvetica", 12)
        p.drawString(100, 780, f"Número: {factura['invoiceNumber']}")
        p.drawString(100, 760, f"Fecha: {factura['issueDate'].strftime('%d/%m/%Y')}")
        
        # Datos del cliente
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, 730, "Datos del Cliente:")
        p.setFont("Helvetica", 12)
        p.drawString(120, 710, f"Nombre: {cliente['name'] if cliente else 'No especificado'}")
        p.drawString(120, 690, f"Identificación: {cliente['identificationNumber'] if cliente else 'No especificado'}")
        
        # Items
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, 660, "Detalle de la Factura:")
        p.setFont("Helvetica", 12)
        
        y = 640
        p.drawString(100, y, "Código")
        p.drawString(200, y, "Descripción")
        p.drawString(350, y, "Cantidad")
        p.drawString(420, y, "P. Unit.")
        p.drawString(500, y, "Subtotal")
        
        y -= 20
        for item in factura['items']:
            p.drawString(100, y, item.get('code', ''))
            p.drawString(200, y, item['name'])
            p.drawString(350, y, str(item['quantity']))
            p.drawString(420, y, f"${item['unitPrice']:.2f}")
            p.drawString(500, y, f"${item['subtotal']:.2f}")
            y -= 20
        
        # Totales
        y -= 20
        p.drawString(400, y, "Subtotal:")
        p.drawString(500, y, f"${factura['subtotal']:.2f}")
        
        y -= 20
        p.drawString(400, y, "IVA (12%):")
        p.drawString(500, y, f"${factura['tax']:.2f}")
        
        y -= 20
        p.setFont("Helvetica-Bold", 14)
        p.drawString(400, y, "TOTAL:")
        p.drawString(500, y, f"${factura['total']:.2f}")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"factura_{factura['invoiceNumber']}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------- Report Routes ----------------------

@app.route('/reportes/productos-stock-bajo', methods=['GET'])
def productos_stock_bajo():
    try:
        productos = list(productos_collection.find({
            '$expr': {'$lt': ['$stock', '$minStock']},
            'status': 'active'
        }).sort('stock', 1))
        
        for producto in productos:
            producto['_id'] = str(producto['_id'])
        
        return jsonify(productos), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/reportes/ventas-por-periodo', methods=['GET'])
def ventas_por_periodo():
    try:
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        
        if not fecha_inicio or not fecha_fin:
            return jsonify({'error': 'Se requieren fecha_inicio y fecha_fin'}), 400
        
        try:
            match_stage = {
                'issueDate': {
                    '$gte': parser.parse(fecha_inicio),
                    '$lte': parser.parse(fecha_fin)
                },
                'status': 'issued'
            }
        except:
            return jsonify({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400
        
        pipeline = [
            {'$match': match_stage},
            {'$group': {
                '_id': None,
                'totalFacturas': {'$sum': 1},
                'totalVentas': {'$sum': '$total'},
                'promedioVenta': {'$avg': '$total'},
                'productosVendidos': {'$sum': {'$sum': '$items.quantity'}}
            }}
        ]
        
        resultado = list(facturas_collection.aggregate(pipeline))
        
        if not resultado:
            return jsonify({
                'totalFacturas': 0,
                'totalVentas': 0,
                'promedioVenta': 0,
                'productosVendidos': 0
            }), 200
        
        return jsonify(resultado[0]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------- Search Routes ----------------------

@app.route('/productos/buscar', methods=['GET'])
def buscar_productos():
    try:
        query = request.args.get('q', '').lower()
        
        if not query:
            return jsonify([]), 200
        
        productos = list(productos_collection.find({
            '$or': [
                {'name': {'$regex': query, '$options': 'i'}},
                {'code': {'$regex': query, '$options': 'i'}},
                {'category': {'$regex': query, '$options': 'i'}}
            ],
            'status': 'active'
        }).limit(10))
        
        resultados = []
        for producto in productos:
            resultados.append({
                '_id': str(producto['_id']),
                'name': producto['name'],
                'code': producto['code'],
                'price': producto['price'],
                'stock': producto['stock'],
                'minStock': producto['minStock']
            })
        
        return jsonify(resultados), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clientes/buscar', methods=['GET'])
def buscar_clientes():
    try:
        identification = request.args.get('identificationNumber', '')
        
        if not identification:
            return jsonify([]), 200
        
        clientes = list(clientes_collection.find({
            'identificationNumber': identification
        }))
        
        resultados = []
        for cliente in clientes:
            resultados.append({
                '_id': str(cliente['_id']),
                'name': cliente['name'],
                'identificationType': cliente['identificationType'],
                'identificationNumber': cliente['identificationNumber'],
                'phone': cliente.get('phone', ''),
                'email': cliente.get('email', '')
            })
        
        return jsonify(resultados), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)