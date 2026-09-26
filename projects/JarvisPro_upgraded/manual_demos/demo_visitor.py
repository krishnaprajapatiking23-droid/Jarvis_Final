from memory.visitor_database import create_tables
from memory.visitor_engine import register_visitor

create_tables()

name = input("Visitor Name: ")

register_visitor(name)

print("Visitor saved successfully!")