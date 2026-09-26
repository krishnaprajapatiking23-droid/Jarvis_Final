def verify(result):

    if result is None:

        return {

            "success": False,

            "message": "Nothing executed."

        }

    # Handle string results
    if isinstance(result, str):

        if result == "FAILED":

            return {

                "success": False,

                "message": "Execution failed."

            }

        return {

            "success": True,

            "message": result

        }

    # Handle dictionary results
    if isinstance(result, dict):

        status = result.get("status")

        if status in ["OPENED", "ALREADY_OPEN"]:

            return {

                "success": True,

                "message": status

            }

        return {

            "success": False,

            "message": status

        }

    return {

        "success": False,

        "message": "Unknown result."

    }