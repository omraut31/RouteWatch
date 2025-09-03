import os
import logging
import re
from twilio.rest import Client
from datetime import datetime

# Twilio credentials
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "your_twilio_account_sid")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "your_twilio_auth_token")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "your_twilio_phone_number")

def send_sos_message(to_phone_number, user_name, latitude, longitude, custom_message=None):
    """
    Send an SOS message using Twilio
    
    Args:
        to_phone_number (str): The recipient's phone number
        user_name (str): The name of the user requesting help
        latitude (float): The user's current latitude
        longitude (float): The user's current longitude
        custom_message (str, optional): Custom message to include
    
    Returns:
        dict: Status of the message send operation
    """
    logging.info(f"Preparing to send SOS message to {to_phone_number}")
    
    try:
        # Validate the phone number first
        if not to_phone_number:
            logging.error("Empty phone number provided")
            return {
                "success": False,
                "error": "Empty phone number provided",
                "timestamp": datetime.now().isoformat()
            }
        
        # Ensure the phone number has a + prefix for the country code
        # If it doesn't start with +, assume it needs proper E.164 formatting
        formatted_number = to_phone_number
        if not to_phone_number.startswith('+'):
            # Remove any non-digit characters
            cleaned_number = re.sub(r'\D', '', to_phone_number)
            
            # Default to US/Canada if no country code (+1)
            if not cleaned_number.startswith('1'):
                cleaned_number = '1' + cleaned_number
            formatted_number = '+' + cleaned_number
            logging.info(f"Reformatted phone number from {to_phone_number} to {formatted_number}")
        
        # Validate the phone number has sufficient digits after formatting
        # Most international numbers should have at least 7 digits plus country code
        digits_only = re.sub(r'\D', '', formatted_number)
        if len(digits_only) < 8:
            logging.error(f"Phone number too short after formatting: {formatted_number} (digits: {len(digits_only)})")
            return {
                "success": False,
                "error": f"Phone number is invalid or too short: {formatted_number}",
                "timestamp": datetime.now().isoformat()
            }
        
        # Check Twilio configuration
        if not TWILIO_ACCOUNT_SID or TWILIO_ACCOUNT_SID == "your_twilio_account_sid":
            logging.error("Twilio account SID not configured")
            return {
                "success": False,
                "error": "Twilio credentials not properly configured",
                "timestamp": datetime.now().isoformat()
            }
            
        if not TWILIO_AUTH_TOKEN or TWILIO_AUTH_TOKEN == "your_twilio_auth_token":
            logging.error("Twilio auth token not configured")
            return {
                "success": False,
                "error": "Twilio credentials not properly configured",
                "timestamp": datetime.now().isoformat()
            }
            
        if not TWILIO_PHONE_NUMBER or TWILIO_PHONE_NUMBER == "your_twilio_phone_number":
            logging.error("Twilio phone number not configured")
            return {
                "success": False,
                "error": "Twilio phone number not properly configured",
                "timestamp": datetime.now().isoformat()
            }
        
        # Create Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Format the message
        google_maps_link = f"https://www.google.com/maps?q={latitude},{longitude}"
        
        message_body = f"SOS ALERT: {user_name} needs emergency assistance! "
        message_body += f"Location: {google_maps_link} "
        
        if custom_message:
            message_body += f"Message: {custom_message} "
            
        message_body += f"Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Send the message
        logging.info(f"Sending SOS message to {formatted_number}: {message_body[:50]}...")
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_number
        )
        
        logging.info(f"SOS message sent to {formatted_number} with SID: {message.sid}")
        
        return {
            "success": True,
            "message_sid": message.sid,
            "recipient": formatted_number,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logging.error(f"Error sending SOS message to {to_phone_number}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "recipient": to_phone_number,
            "timestamp": datetime.now().isoformat()
        }

def send_multiple_sos_messages(emergency_contacts, user_name, latitude, longitude, custom_message=None):
    """
    Send SOS messages to multiple emergency contacts
    
    Args:
        emergency_contacts (list): List of emergency contact objects with phone numbers
        user_name (str): The name of the user requesting help
        latitude (float): The user's current latitude
        longitude (float): The user's current longitude
        custom_message (str, optional): Custom message to include
    
    Returns:
        dict: Results of all message send operations
    """
    if not emergency_contacts:
        logging.error("No emergency contacts provided")
        return {
            "success": False,
            "error": "No emergency contacts provided",
            "results": [],
            "timestamp": datetime.now().isoformat()
        }
    
    logging.info(f"Sending SOS messages to {len(emergency_contacts)} contacts")
    results = []
    successful_sends = 0
    
    for contact in emergency_contacts:
        try:
            logging.info(f"Sending SOS to {contact.name} at {contact.phone}")
            result = send_sos_message(
                contact.phone,
                user_name,
                latitude,
                longitude,
                custom_message
            )
            
            # Track successful sends
            if result.get("success", False):
                successful_sends += 1
                
            results.append({
                "contact_name": contact.name,
                "contact_phone": contact.phone,
                "relationship": getattr(contact, 'relationship', 'Not specified'),
                "result": result
            })
        except Exception as e:
            logging.error(f"Error processing contact {getattr(contact, 'name', 'Unknown')}: {str(e)}")
            results.append({
                "contact_name": getattr(contact, 'name', 'Unknown'),
                "contact_phone": getattr(contact, 'phone', 'Unknown'),
                "result": {
                    "success": False,
                    "error": f"Failed to process contact: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                }
            })
    
    # Consider partial success if at least one message was sent
    overall_success = successful_sends > 0
    
    response = {
        "success": overall_success,
        "total_contacts": len(emergency_contacts),
        "successful_sends": successful_sends,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }
    
    if not overall_success:
        response["error"] = "Failed to send any SOS messages"
    elif successful_sends < len(emergency_contacts):
        response["warning"] = f"Only {successful_sends} of {len(emergency_contacts)} messages were sent successfully"
    
    logging.info(f"SOS message sending complete: {successful_sends}/{len(emergency_contacts)} successful")
    return response
