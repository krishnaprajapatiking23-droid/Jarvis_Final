from memory.visitor_database import connect

conn = connect()
cursor = conn.cursor()

cursor.execute(
    "DELETE FROM visitors WHERE LOWER(name)='krishna'"
)

conn.commit()
conn.close()

print("Owner removed from visitor database.")