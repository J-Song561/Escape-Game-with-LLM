using System;

[Serializable]
public class Message
{
    public string role;
    public string content;
}

[Serializable]
public class ChatRequest
{
    public string npc;
    public Message[] messages;
    public string session_id;
}

[Serializable]
public class ChatResponse
{
    public string reply;
    public string npc;
}