package example;

import org.junit.Test;
import static org.junit.Assert.*;

public class OrderTest {
    @Test public void calculatesTotal() {
        assertEquals(100, Order.total(25, 4));
    }

    @Test(expected = IllegalArgumentException.class) public void rejectsNegativeQuantity() {
        Order.total(25, -1);
    }
}
