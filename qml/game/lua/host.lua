-- GG frame/event interface adapted from Benilla. Uses its Lua 5.0 grammar.
local frames, byname, snapshot = {}, {}, {}
local methods = {}
local count = 0
function GG_Utf8Prefix(value,limit)
    local text=tostring(value or "")
    if string.len(text)<=limit then return text end
    local n=limit
    local byte=string.byte(text,n+1)
    while n>0 and byte>=128 and byte<192 do
        n=n-1
        byte=string.byte(text,n+1)
    end
    return string.sub(text,1,n)
end
local function bounded(value, limit)
    return GG_Utf8Prefix(value,limit)
end
function CreateFrame(kind, name, parent)
    assert(kind == "Frame" or kind == "Button" or kind == "StatusBar", "unsupported frame type")
    name = bounded(name,96)
    assert(name ~= "" and not byname[name], "duplicate or empty frame name")
    assert(count < 64, "frame capacity exceeded")
    count = count + 1
    local f = {id=name,kind=kind,x=12,y=120,width=220,height=64,text="",visible=true,
        value=0,color="#d3ac63",background="#dd19232b",events={},scripts={},level=count}
    setmetatable(f,{__index=methods})
    frames[count], byname[name] = f, f
    return f
end
function methods:SetText(text) self.text = bounded(text,512) end
function methods:SetSize(w,h) self.width=math.max(16,math.min(640,w));self.height=math.max(16,math.min(400,h)) end
function methods:SetPoint(point,parent,relative,x,y)
    assert(point=="TOPLEFT", "first GG layout supports TOPLEFT anchors")
    self.x=math.max(0,math.min(4096,x or 0));self.y=math.max(0,math.min(4096,-(y or 0)))
end
function methods:SetFrameLevel(level) self.level=math.max(0,math.min(1000,level)) end
function methods:SetValue(value) self.value=math.max(0,math.min(1,value)) end
function methods:SetColor(color) assert(string.find(color,"^#%x%x%x%x%x%x$"),"invalid color");self.color=color end
function methods:Show() self.visible=true end
function methods:Hide() self.visible=false end
function methods:IsShown() return self.visible end
function methods:RegisterEvent(name) self.events[bounded(name,64)]=true end
function methods:UnregisterEvent(name) self.events[name]=nil end
function methods:SetScript(name, fn)
    assert(name=="OnEvent" or name=="OnClick", "unsupported handler")
    assert(type(fn)=="function" or fn==nil,"handler must be a function")
    self.scripts[name]=fn
end
function GetSnapshot() return snapshot end
function UnitHealth(unit) if unit=="player" then return snapshot.health or 100 end return 0 end
function GG_Publish(x,y,z,yaw,time,speed,health,resource,running,cell,biome)
    snapshot={x=x,y=y,z=z,yaw=yaw,time=time,speed=speed,health=health,resource=resource,running=running,cell=cell,biome=biome}
end
local function fire(f,script,name,payload)
    local fn=f.scripts[script]
    if not fn then return end
    local previous_this,previous_event,previous_arg=this,event,arg1
    this,event,arg1=f,name,payload
    fn(f,name,payload)
    this,event,arg1=previous_this,previous_event,previous_arg
end
function GG_Dispatch(name,payload)
    local n=count
    for i=1,n do local f=frames[i];if f.events[name] then fire(f,"OnEvent",name,payload) end end
end
function GG_Click(id)
    local f=byname[id];assert(f and f.visible and f.kind=="Button","unknown or hidden button")
    fire(f,"OnClick","CLICK","")
end
local function quote(value)
    local text=bounded(value,512)
    text=string.gsub(text,'[%z\1-\31\\"]',function(c)
        if c=='"' then return '\\"' elseif c=='\\' then return '\\\\' end
        return string.format('\\u%04x',string.byte(c))
    end)
    return '"'..text..'"'
end
function GG_DrawJson()
    local out={}
    for i=1,count do
        local f=frames[i]
        out[i]='{"id":'..quote(f.id)..',"kind":'..quote(f.kind)..',"x":'..f.x..',"y":'..f.y
            ..',"width":'..f.width..',"height":'..f.height..',"text":'..quote(f.text)
            ..',"visible":'..tostring(f.visible)..',"value":'..f.value..',"color":'..quote(f.color)
            ..',"background":'..quote(f.background)..',"level":'..f.level..'}'
    end
    return '['..table.concat(out,',')..']'
end
