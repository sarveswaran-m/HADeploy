

class Plugin:
    def __init__(self):
        self.name = None
        self.path = None
    

class Context:
    def __init__(self):
        pass
        
        
        
    

def main():
    print "Allo"
    ctx = Context()
    ctx.xxx = "xxx"
    
    print ctx.xxx
    #print ctx.pluginByName['abc'].path




if __name__ == "__main__":
    main()


