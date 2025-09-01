from flask import Flask, render_template
import sqlite3
import os
import datetime

app = Flask(__name__)

@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect('/data/entries.db')
    c = conn.cursor()
    current_month = datetime.datetime.now().strftime("%B-%Y")
    c.execute("SELECT user_id, SUM(entry_count) as total FROM entries WHERE month_year = ? GROUP BY user_id ORDER BY total DESC", (current_month,))
    data = c.fetchall()
    labels = []
    values = []
    for user_id, total in data:
        try:
            # Fetch display name (simplified, adjust with bot if needed)
            labels.append("User_" + user_id[-4:])  # Placeholder, improve with bot fetch
            values.append(total)
        except Exception:
            continue
    conn.close()
    return render_template('dashboard.html', labels=labels, values=values)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)