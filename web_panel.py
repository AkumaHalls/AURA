import os
import functools
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

PANEL_PASSWORD = os.getenv("WEB_PANEL_PASSWORD")

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
app.secret_key = os.urandom(24).hex()

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if request.form.get('password') == PANEL_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        flash('Senha incorreta.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.errorhandler(500)
def server_error(e):
    return render_template('login.html', error_msg="Erro interno no servidor. Verifique os logs."), 500

@app.errorhandler(404)
def not_found(e):
    return render_template('login.html', error_msg="Página não encontrada."), 404

@app.route('/')
@login_required
def dashboard():
    try:
        from mongo_db import stats_dashboard, listar_provas
        stats = stats_dashboard()
        provas = listar_provas(10)
        return render_template('dashboard.html', active='dashboard', stats=stats, provas_recentes=provas)
    except Exception as e:
        return render_template('dashboard.html', active='dashboard',
                               stats={"total_provas": 0, "aprovados": 0, "reprovados": 0, "total_tickets": 0},
                               provas_recentes=[]), 200

@app.route('/provas', methods=['GET', 'POST'])
@login_required
def provas():
    if request.method == 'POST':
        from mongo_db import deletar_prova
        user_id = request.form.get('user_id')
        date = request.form.get('date')
        if user_id and date:
            ok = deletar_prova(user_id, date)
            flash('Prova deletada com sucesso.' if ok else 'Erro ao deletar prova.', 'success' if ok else 'danger')
        else:
            flash('Dados insuficientes para deletar.', 'danger')
        return redirect(url_for('provas'))
    try:
        from mongo_db import listar_provas
        todas = listar_provas(200)
    except Exception:
        todas = []
    return render_template('provas.html', active='provas', provas=todas)

@app.route('/tickets', methods=['GET', 'POST'])
@login_required
def tickets():
    if request.method == 'POST':
        from mongo_db import deletar_ticket
        user_id = request.form.get('user_id')
        data = request.form.get('data')
        if user_id and data:
            ok = deletar_ticket(user_id, data)
            flash('Ticket deletado com sucesso.' if ok else 'Erro ao deletar ticket.', 'success' if ok else 'danger')
        else:
            flash('Dados insuficientes para deletar.', 'danger')
        return redirect(url_for('tickets'))
    try:
        from mongo_db import listar_tickets
        todos = listar_tickets(200)
    except Exception:
        todos = []
    return render_template('tickets.html', active='tickets', tickets=todos)

@app.route('/clan')
@login_required
def clan():
    dados = {"member_count": 0, "level": 0, "points": 0, "war_wins": 0, "members": []}
    error = None
    try:
        import coc
        import asyncio
        email = os.getenv("COC_EMAIL")
        password = os.getenv("COC_PASSWORD")
        tag = os.getenv("CLAN_TAG")
        if email and password and tag:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            client = coc.Client(key_count=1, key_names="WebPanelKey", throttle_limit=10)
            try:
                loop.run_until_complete(client.login(email, password))
                clan_data = loop.run_until_complete(client.get_clan(tag))
                dados = {
                    "member_count": clan_data.member_count,
                    "level": clan_data.level,
                    "points": clan_data.points,
                    "war_wins": clan_data.war_wins,
                    "members": [
                        {"name": m.name, "role": m.role.in_game_name, "trophies": m.trophies, "exp_level": m.exp_level}
                        for m in clan_data.members
                    ]
                }
            finally:
                try: loop.run_until_complete(client.close())
                except: pass
        else:
            error = "COC_EMAIL, COC_PASSWORD ou CLAN_TAG não configurados no .env"
    except Exception as e:
        error = f"Erro: {e}"
    return render_template('clan.html', active='clan', clan_data=dados, error=error)

def run_web_panel():
    if not PANEL_PASSWORD:
        print("WEB_PANEL_PASSWORD não configurado. Painel web desabilitado.")
        return
    from mongo_db import conectar
    conectar()
    print(f"Painel web rodando em http://0.0.0.0:2501")
    app.run(host="0.0.0.0", port=2501, debug=False, use_reloader=False)