from Security_Leroy import app, database as db

with app.app_context():
    db.drop_all()
    print("Banco deletado.")
    db.create_all()
    print("Banco Criado.")


# with app.app_context():
#     database.drop_all()
#     database.create_all()
#     print("Banco recriado.")

#
# with app.app_context():
#     usuario = Usuarios(username='And', email='andpanda@gmail.com', senha='1234567')
#     usuario2 = Usuarios(username='Marry', email='marry@gmail.com', senha='1234567')
#
#     database.session.add(usuario)
#     database.session.add(usuario2)
#
#     database.session.commit()
# Um comando so <>
# email = 'andpanda@gmail.com'
# with app.app_context():
#     meus_usuarios = Usuarios.query.filter_by(email=email).first()
#     print(meus_usuarios)
#<>

# with app.app_context():
#    meus_usuarios = Usuarios.query.filter_by(id=1).first()
#    print(meus_usuarios.username)

# with app.app_context():
#    meus_posts = Post(id_usuario=1, titulo='Primeiro Post ', corpo='Arregacei')
#    database.session.add(meus_posts)
#    database.session.commit()
#    print(meus_posts)

# with app.app_context():
#     meus_posts = Post.query.first()
#     print(meus_posts.data_criacao)

    # main.py


#with app.app_context():
    #db.drop_all()
    #db.create_all()
   # print("✅ Banco recriado.")

#     # (opcional) criar 1 usuário de teste já com senha hash
#     senha_hash = bcrypt.generate_password_hash("1234567").decode("utf-8")
#     u = Usuarios(username="And", email="and@gmail.com", senha=senha_hash)
#     db.session.add(u)
#     db.session.commit()
#     print("👤 Usuário seed criado: and@gmail.com / 1234567")