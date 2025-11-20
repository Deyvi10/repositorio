# -*- coding: utf-8 -*-
{
    'name': "biblioteca",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/cron.xml',
        'views/wizard_views.xml',
        'views/Libro_views.xml',
        'views/Autor_views.xml',
        'views/Editorial_views.xml',
        'views/Genero_views.xml',
        'views/Ubicacion_views.xml',
        'views/Usuario_views.xml',
        'views/Prestamo_views.xml',
        'views/Personal_views.xml',
        'views/Multa_views.xml',
        'views/views.xml',
        #'views/templates.xml',
    ],
    # only loaded in demonstration mode
    #'demo': [
    #    'demo/demo.xml',
    #],
    'application': True,
    'license': 'AGPL-3' 
}