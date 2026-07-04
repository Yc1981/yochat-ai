import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import websockets
import asyncio

load_dotenv()

app = FastAPI(title="YoChat Live Teacher Backend")

# Configure CORS
allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash-live-001")
GEMINI_LIVE_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"


@app.get("/")
def root():
    return {
        "service": "YoChat Live Teacher Backend",
        "status": "running",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "key_configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL,
        "api_version": "v1beta",
    }


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    query_params = websocket.query_params
    grade = query_params.get("grade", "6th Grade")
    unit = query_params.get("unit", "Unit 1")
    lesson = query_params.get("lesson", "Lesson 1")
    scenario = query_params.get("scenario", "")
    voice = query_params.get("voice", "Aoede")
    teacher_name = query_params.get("teacherName", "Ons")

    await websocket.accept()

    if not GEMINI_API_KEY:
        await websocket.send_json({
            "type": "error",
            "message": "GEMINI_API_KEY environment variable is missing on the server.",
        })
        await websocket.close()
        return

    print(f"Accepted student connection for {grade} - {lesson} with teacher {teacher_name}")

    is_yamen = teacher_name.lower() == "yamen"
    role_desc = "Mr. Yamen, a friendly and warm male" if is_yamen else "Mrs. Ons, a friendly and warm female"
    system_instruction = (
        f"You are {role_desc} English teacher for Tunisian {grade} learners.\n"
        "Speak slowly and clearly.\n"
        "Use simple A1/A2 English.\n"
        "Ask one question at a time.\n"
        "Correct mistakes gently.\n"
        "Encourage the learner.\n"
        f"Selected Unit: {unit}\n"
        f"Selected Lesson: {lesson}\n"
        f"Selected Role-play Scenario: {scenario}\n\n"
        "Start by greeting the learner and asking the first role-play question. "
        "Do not give long explanations. Keep the conversation oral and interactive."
    )

    gemini_config = {
        "setup": {
            "model": GEMINI_MODEL,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice,
                        }
                    }
                },
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}],
            },
        }
    }

    uri = f"{GEMINI_LIVE_URL}?key={GEMINI_API_KEY}"

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as gemini_ws:
            await gemini_ws.send(json.dumps(gemini_config))
            print(f"Sent Gemini Live setup config. Model: {GEMINI_MODEL}")

            setup_ready = False
            for _ in range(10):
                raw_setup_response = await asyncio.wait_for(gemini_ws.recv(), timeout=10)
                setup_response = json.loads(raw_setup_response)
                print(f"Gemini setup response: {setup_response}")

                if setup_response.get("setupComplete") is not None:
                    setup_ready = True
                    break

                if "error" in setup_response:
                    raise RuntimeError(setup_response["error"])

            if not setup_ready:
                raise RuntimeError("Gemini Live did not confirm setupComplete.")

            await websocket.send_json({
                "type": "connected",
                "message": "YoChat is ready! Speak into your microphone.",
            })

            async def client_to_gemini():
                try:
                    while True:
                        raw_data = await websocket.receive_text()
                        msg = json.loads(raw_data)

                        if msg.get("type") == "audio" and msg.get("data"):
                            audio_payload = {
                                "realtimeInput": {
                                    "mediaChunks": [
                                        {
                                            "data": msg["data"],
                                            "mimeType": "audio/pcm;rate=16000",
                                        }
                                    ]
                                }
                            }
                            await gemini_ws.send(json.dumps(audio_payload))
                except WebSocketDisconnect:
                    print("Student client disconnected")
                except Exception as e:
                    print(f"Error in client_to_gemini: {e}")

            async def gemini_to_client():
                try:
                    async for raw_response in gemini_ws:
                        response = json.loads(raw_response)
                        print(f"Gemini response keys: {list(response.keys())}")

                        server_content = response.get("serverContent", {})
                        model_turn = server_content.get("modelTurn", {})
                        parts = model_turn.get("parts", [])

                        for part in parts:
                            if "inlineData" in part and part["inlineData"].get("data"):
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": part["inlineData"]["data"],
                                })

                            if "text" in part:
                                await websocket.send_json({
                                    "type": "text",
                                    "data": part["text"],
                                })

                        if server_content.get("interrupted"):
                            await websocket.send_json({"type": "interrupted"})

                except Exception as e:
                    print(f"Error in gemini_to_client: {e}")

            await asyncio.gather(client_to_gemini(), gemini_to_client())

    except Exception as e:
        print(f"Failed to bridge connection to Gemini Live: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Gemini connection failed: {str(e)}",
            })
        except Exception:
            pass

    print("WebSocket session closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
