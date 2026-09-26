from reasoning.manager import reason

context = {

    "notepad": True,

    "chrome": False

}

print(

    reason(

        "Open Notepad",

        context

    )

)