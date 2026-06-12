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
}

[Serializable]
public class ChatResponse
{
    public string reply;
    public string npc;
}