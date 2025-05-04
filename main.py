from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import db_helper
import generic_helper

app = FastAPI()

inprogress_orders = {}


@app.post("/")
async def handle_request(request: Request) -> JSONResponse:
    try:
        payload = await request.json()

        intent = payload['queryResult']['intent']['displayName']
        parameters = payload['queryResult']['parameters']
        output_contexts = payload['queryResult']['outputContexts']
        session_id = generic_helper.extract_session_id(output_contexts[0]["name"])

        intent_handler_dict = {
            'order.add context:ongoing order': add_to_order,
            'order.remove-context:ongoing order': remove_from_order,
            'order.complete context:ongoing order': complete_order,
            'track.order-context:ongoing order': track_order,
        }

        handler = intent_handler_dict.get(intent)
        if handler:
            return handler(parameters, session_id)
        else:
            return JSONResponse(content={
                "fulfillmentText": f"Sorry, I don't know how to handle the intent '{intent}'."
            })

    except Exception as e:
        return JSONResponse(content={
            "fulfillmentText": f"An error occurred: {str(e)}"
        })


def save_to_db(order: dict) -> int:
    next_order_id = db_helper.get_next_order_id()

    for food_item, quantity in order.items():
        rcode = db_helper.insert_order_item(food_item, quantity, next_order_id)
        if rcode == -1:
            return -1

    db_helper.insert_order_tracking(next_order_id, "in progress")
    return next_order_id


def complete_order(_: dict, session_id: str) -> JSONResponse:
    if session_id not in inprogress_orders:
        fulfillment_text = "I'm having trouble finding your order. Sorry! Can you place a new order, please?"
    else:
        order = inprogress_orders[session_id]
        order_id = save_to_db(order)
        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. Please place a new order again."
        else:
            order_total = db_helper.get_total_order_price(order_id)
            fulfillment_text = (
                f"Awesome. We have placed your order. "
                f"Here is your order id # {order_id}. "
                f"Your order total is {order_total} which you can pay at the time of delivery!"
            )
        del inprogress_orders[session_id]

    return JSONResponse(content={"fulfillmentText": fulfillment_text})


def add_to_order(parameters: dict, session_id: str) -> JSONResponse:
    food_items = parameters.get("food-item", [])
    quantities = parameters.get("number", [])

    if len(food_items) != len(quantities):
        fulfillment_text = "Sorry, I didn't understand. Can you please specify food items and quantities clearly?"
    else:
        new_food_dict = dict(zip(food_items, quantities))

        if session_id in inprogress_orders:
            current_food_dict = inprogress_orders[session_id]
            current_food_dict.update(new_food_dict)
        else:
            inprogress_orders[session_id] = new_food_dict

        order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
        fulfillment_text = f"So far you have: {order_str}. Do you need anything else?"

    return JSONResponse(content={"fulfillmentText": fulfillment_text})


def remove_from_order(parameters: dict, session_id: str) -> JSONResponse:
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having trouble finding your order. Sorry! Can you place a new order please?"
        })

    food_items = parameters.get("food-item", [])
    current_order = inprogress_orders[session_id]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item in current_order:
            removed_items.append(item)
            del current_order[item]
        else:
            no_such_items.append(item)

    messages = []
    if removed_items:
        messages.append(f"Removed {', '.join(removed_items)} from your order.")
    if no_such_items:
        messages.append(f"Your current order does not have {', '.join(no_such_items)}.")

    if not current_order:
        messages.append("Your order is now empty!")
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        messages.append(f"Here is what is left in your order: {order_str}")

    return JSONResponse(content={"fulfillmentText": " ".join(messages)})


def track_order(parameters: dict, _: str) -> JSONResponse:
    try:
        order_id = int(parameters['number'])
        order_status = db_helper.get_order_status(order_id)
        if order_status:
            fulfillment_text = f"The order status for order id: {order_id} is: {order_status}"
        else:
            fulfillment_text = f"No order found with order id: {order_id}"
    except (ValueError, KeyError, TypeError):
        fulfillment_text = "Invalid order ID provided."

    return JSONResponse(content={"fulfillmentText": fulfillment_text})
