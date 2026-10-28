package example;

import javax.xml.bind.JAXBContext;

public final class LegacyXml {
    private LegacyXml() {}
    public static JAXBContext context() throws Exception {
        return JAXBContext.newInstance(Object.class);
    }
}
